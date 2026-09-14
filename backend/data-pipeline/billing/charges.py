"""The usage reports data-pipeline sends, one per unit of metered work.

Operations and categories follow the table in docs/billing/credit-system-api.md:

| operation             | category                                   | items                                   |
|-----------------------|--------------------------------------------|-----------------------------------------|
| document.ingest       | DOCUMENTS (uploads, attachments, URLs) or  | LLAMAPARSE_PAGE + TOKENS (scorer,       |
|                       | CONNECTORS (synced items)                  | classifier, embeddings)                 |
| document.reclassify   | DOCUMENTS                                  | TOKENS                                  |
| knowledge.search      | SEARCH                                     | TOKENS (query embedding)                |
| catalog.ai            | CATALOG                                    | TOKENS                                  |
| connector.sync        | CONNECTORS                                 | COMPOSIO_EXECUTION                      |

Every report carries a stable idempotency key, so a retry (of the work, or of the report itself) is
never charged twice. Reporting never raises.
"""
from __future__ import annotations

import hashlib
import logging
import uuid
from dataclasses import dataclass
from typing import Any, Optional

from billing.client import canonical_uuid, get_billing_client
from billing.metering import MAX_ITEMS, UsageMeter

logger = logging.getLogger("billing")

OP_DOCUMENT_INGEST = "document.ingest"
OP_DOCUMENT_RECLASSIFY = "document.reclassify"
OP_KNOWLEDGE_SEARCH = "knowledge.search"
OP_CATALOG_AI = "catalog.ai"
OP_CONNECTOR_SYNC = "connector.sync"

CATEGORY_DOCUMENTS = "DOCUMENTS"
CATEGORY_CONNECTORS = "CONNECTORS"
CATEGORY_SEARCH = "SEARCH"
CATEGORY_CATALOG = "CATALOG"

# Keys are unique in billing-service's ledger, which stores up to 255 characters and prefixes
# "usage:" for the credit transaction. A longer key (a connector document id can be long) is replaced
# by a digest of itself, which is just as stable.
MAX_KEY_LENGTH = 200


def idempotency_key(operation: str, *parts: Any) -> str:
    """``operation:part:part...`` (empty parts left out), or a digest of it when too long."""
    raw = ":".join([operation, *(str(part) for part in parts if part not in (None, ""))])
    if len(raw) <= MAX_KEY_LENGTH:
        return raw
    return f"{operation}:sha256:{hashlib.sha256(raw.encode('utf-8')).hexdigest()}"


def new_run_id() -> str:
    return uuid.uuid4().hex


def hash_content(content: Any) -> str:
    """sha256 of the bytes (or text) that were ingested."""
    if content is None:
        return ""
    data = content if isinstance(content, (bytes, bytearray)) else str(content).encode("utf-8", errors="replace")
    return hashlib.sha256(bytes(data)).hexdigest()


def document_category(source: Any) -> str:
    """CONNECTORS for a document synced from a connected app, DOCUMENTS for everything else."""
    from module_1_document_processing.connector_privacy import is_connector_source

    return CATEGORY_CONNECTORS if is_connector_source(source) else CATEGORY_DOCUMENTS


def report_usage(
    *,
    operation: str,
    category: str,
    workspace_id: Any,
    user_id: Any,
    idempotency_key: str,
    meter: UsageMeter | list[dict[str, Any]] | None,
    reference: Any = None,
    metadata: Optional[dict[str, Any]] = None,
) -> bool:
    """Hand one usage report to the billing client. Returns False when there was nothing to report.

    Work that has no workspace (legacy or system data) is not charged. A user id that is not a UUID
    (billing-service stores user ids as UUIDs) is sent as null and kept in the metadata instead.
    """
    try:
        workspace = canonical_uuid(workspace_id)
        if workspace is None:
            logger.debug("[Billing] %s (%s) has no workspace; not charged.", operation, reference)
            return False
        items = meter.items() if isinstance(meter, UsageMeter) else list(meter or [])
        if not items:
            return False

        details = dict(metadata or {})
        if isinstance(meter, UsageMeter):
            details.setdefault("usage", meter.purposes())
        user = canonical_uuid(user_id)
        if user_id and user is None:
            details["actorId"] = str(user_id)[:128]

        get_billing_client().charge(
            {
                "workspaceId": workspace,
                "userId": user,
                "operation": operation,
                "category": category,
                "idempotencyKey": idempotency_key,
                "reference": str(reference)[:255] if reference else None,
                "items": items[:MAX_ITEMS],
                "metadata": {key: value for key, value in details.items() if value not in (None, "", [], {})},
            }
        )
        return True
    except Exception as err:
        print(f"[Billing] ERROR could not report {operation} usage ({type(err).__name__}: {err}).")
        return False


# ---- document ingestion ------------------------------------------------------
@dataclass
class IngestCharge:
    """Charges one document's ingestion once: parsing (LlamaParse pages), the gatekeeper's scorer, the
    classifier and embedding, in a single ``document.ingest`` report when the document's processing ends.

    Ingestion runs in stages (parse and classify, then embed as its own queue job), so the usage of an
    earlier stage is carried in the next stage's job (``carry``) and reported with it. A document that
    stops early - held by the gatekeeper, unreadable, quarantined - is reported where it stops.

    Key: document id + a hash of the ingested content + the run + the stage it stopped at.
    - A retry of a queue job reuses the job's run and content, so it is never charged twice.
    - A knowledge-vault upload, URL ingest or reindex queues a new run, so processing a document again
      on purpose is charged again. (Re-uploading a file that is already indexed never queues anything.)
    - A connector document has no run: the same synced content is charged once however often a sync
      or webhook delivers it, and charged again when its content changes.
    """

    workspace_id: str
    user_id: str
    doc_id: str
    source: str
    run_id: str = ""
    content_hash: str = ""
    carried: Optional[dict[str, Any]] = None

    @classmethod
    def for_job(
        cls,
        billing: Any,
        *,
        workspace_id: Any,
        user_id: Any,
        doc_id: Any,
        source: Any,
        content: Any = None,
    ) -> "IngestCharge":
        """The charge for a queued job. ``billing`` is what the job's payload carries (see ``carry``)."""
        info = billing if isinstance(billing, dict) else {}
        usage = info.get("usage")
        return cls(
            workspace_id=str(workspace_id or ""),
            # The person who started the work (e.g. who clicked reindex), else the document's owner.
            user_id=str(info.get("user_id") or user_id or ""),
            doc_id=str(doc_id or ""),
            source=str(source or ""),
            run_id=str(info.get("run_id") or ""),
            content_hash=str(info.get("content_hash") or hash_content(content)),
            carried=usage if isinstance(usage, dict) else None,
        )

    def total(self, meter: Optional[UsageMeter]) -> UsageMeter:
        return UsageMeter.from_dict(self.carried).merge(meter)

    def carry(self, meter: Optional[UsageMeter]) -> dict[str, Any]:
        """The ``billing`` entry for the next stage's job: this run, and all usage spent so far."""
        return {
            "run_id": self.run_id,
            "user_id": self.user_id,
            "content_hash": self.content_hash,
            "usage": self.total(meter).to_dict(),
        }

    def charge(self, stage: str, meter: Optional[UsageMeter]) -> bool:
        total = self.total(meter)
        return report_usage(
            operation=OP_DOCUMENT_INGEST,
            category=document_category(self.source),
            workspace_id=self.workspace_id,
            user_id=self.user_id,
            idempotency_key=idempotency_key(OP_DOCUMENT_INGEST, self.doc_id, self.content_hash[:16], self.run_id, stage),
            meter=total,
            reference=self.doc_id,
            metadata={"stage": stage, "source": self.source, "run": self.run_id},
        )


# ---- single requests ---------------------------------------------------------
# A request has no natural id, so each charge gets a fresh one. The key is fixed when the report is
# built, and a report that has to be retried is resent with it.
def charge_reclassify(*, workspace_id: Any, user_id: Any, doc_id: str, meter: UsageMeter) -> bool:
    return report_usage(
        operation=OP_DOCUMENT_RECLASSIFY,
        category=CATEGORY_DOCUMENTS,
        workspace_id=workspace_id,
        user_id=user_id,
        idempotency_key=idempotency_key(OP_DOCUMENT_RECLASSIFY, doc_id, new_run_id()),
        meter=meter,
        reference=doc_id,
    )


def charge_knowledge_search(*, workspace_id: Any, user_id: Any, meter: UsageMeter) -> bool:
    return report_usage(
        operation=OP_KNOWLEDGE_SEARCH,
        category=CATEGORY_SEARCH,
        workspace_id=workspace_id,
        user_id=user_id,
        idempotency_key=idempotency_key(OP_KNOWLEDGE_SEARCH, new_run_id()),
        meter=meter,
    )


def charge_catalog_ai(*, workspace_id: Any, user_id: Any, feature: str, meter: UsageMeter) -> bool:
    return report_usage(
        operation=OP_CATALOG_AI,
        category=CATEGORY_CATALOG,
        workspace_id=workspace_id,
        user_id=user_id,
        idempotency_key=idempotency_key(OP_CATALOG_AI, feature, new_run_id()),
        meter=meter,
        metadata={"feature": feature},
    )


# ---- connectors ----------------------------------------------------------------
def charge_connector_sync(
    *,
    workspace_id: Any,
    user_id: Any,
    source: str,
    meter: UsageMeter,
    run_id: Optional[str] = None,
    trigger: str = "",
    reference: Any = None,
) -> bool:
    """The Composio executions one sync run (or webhook, or reconciliation listing) made."""
    return report_usage(
        operation=OP_CONNECTOR_SYNC,
        category=CATEGORY_CONNECTORS,
        workspace_id=workspace_id,
        user_id=user_id,
        idempotency_key=idempotency_key(OP_CONNECTOR_SYNC, source, run_id or new_run_id()),
        meter=meter,
        reference=reference,
        metadata={"source": source, "trigger": trigger},
    )
