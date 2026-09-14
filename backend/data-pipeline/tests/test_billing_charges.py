"""What each piece of metered work is charged, end to end through the real pipeline code.

Only the edges are fake: LlamaParse's client, the Gemini and OpenRouter HTTP endpoints, the vector
storage, Composio's tools, and billing-service itself (tests/fake_billing.py, which de-duplicates by
idempotency key like the real service, so "billed" below means what a workspace would pay).
"""
import asyncio
import base64
import json
import uuid
from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import UUID

import pytest
import requests
from fastapi import FastAPI
from fastapi.testclient import TestClient

from billing.connectors import metered_sync_run
from billing.metering import estimate_tokens, record_composio_execution
from catalog.auth import CatalogContext, get_catalog_context
from catalog.routes import get_service
from catalog.routes import router as catalog_router
from catalog.schemas import SemanticSearchResponse
from catalog.service import ProductService
from module_1_document_processing import knowledge_vault_routes as kv
from module_1_document_processing import workspace_access
from module_1_document_processing.composio_connector import gdrive_sync_manager as gdrive_module
from module_1_document_processing.composio_connector.calendar_store import CalendarStore
from module_1_document_processing.composio_connector.calendar_sync_manager import CalendarSyncManager
from module_1_document_processing.composio_connector.events.canonical_event import CanonicalEvent, EventType
from module_1_document_processing.composio_connector.gdrive_models import GDriveTriggerType
from module_1_document_processing.composio_connector.gdrive_store import GDriveStore
from module_1_document_processing.composio_connector.gdrive_sync_manager import GDriveSyncManager
from module_1_document_processing.composio_connector.gmail_store import GmailStore
from module_1_document_processing.composio_connector.gmail_sync_manager import GmailSyncManager
from module_1_document_processing.composio_connector.notion_store import NotionStore
from module_1_document_processing.composio_connector.notion_sync_manager import NotionSyncManager
from module_1_document_processing.composio_connector.slack_store import SlackStore
from module_1_document_processing.composio_connector.slack_sync_manager import SlackSyncManager
from module_1_document_processing.del_acl_and_reconc import reconciliation_scheduler as scheduler_module
from module_1_document_processing.del_acl_and_reconc.reconciliation_scheduler import ReconciliationScheduler
from module_1_document_processing.pipeline.durable_queue import ingest_queue
from module_1_document_processing.pipeline.job_payloads import JOB_DOCUMENT_EMBED, JOB_DOCUMENT_INGEST
from module_1_document_processing.pipeline.queue_worker import QueueWorker
from module_1_document_processing.workspace_access import MembershipDirectory
from module_2_memory_gatekeeper.policy import DEFAULT_SEMANTIC_MODEL
from module_3_batch_ingestion_vector.chunker import TextNode
from module_3_batch_ingestion_vector.embedding_worker import EmbeddingWorker
from tests.fake_billing import billing, items_by_kind  # noqa: F401 - fixture
from tests.test_connector_workspace_scope import SCHEDULERS, _due_connection, _Store, _Worker

WORKSPACE = str(uuid.uuid4())
MEMBER = str(uuid.uuid4())
REP = str(uuid.uuid4())
ROLES = {MEMBER: {WORKSPACE: "MEMBER"}, REP: {WORKSPACE: "MEMBER"}}
HEADERS = {"X-User-Id": MEMBER, "X-Tenant-Id": WORKSPACE}

SERVED_MODEL = "nvidia/nemotron-3-super-120b-a12b:free"
EMBEDDING_MODEL = "gemini-embedding-2"
PAGES = [
    "Enterprise pricing tiers: Starter at 19 dollars per seat, Pro at 49 dollars per seat, Business at 149.",
    "Discount bands for multi-year agreements and volume purchases, with approval rules for sales managers.",
    "Renewal terms, payment schedule and service level commitments for enterprise customers in fintech.",
]
PARSED_TEXT = "\n\n".join(PAGES)
PDF_BYTES = b"%PDF-1.7\n" + b"pricing document body " * 20
CLASSIFICATION = {
    "category": "PRICING_PACKAGING", "target_competitor": None, "target_industry": "Fintech",
    "sales_summary": "Enterprise pricing tiers and discount bands.", "sales_tags": ["pricing"], "confidence_score": 0.9,
}


class FakeResponse:
    def __init__(self, status_code=200, body=None):
        self.status_code = status_code
        self._body = body
        self.text = json.dumps(body) if body is not None else ""
        self.headers = {}

    def json(self):
        return self._body


class Providers:
    """Gemini (gatekeeper scorer, embeddings) and OpenRouter (classifier, catalog AI), faked by URL."""

    def __init__(self):
        self.score = 0.9
        self.urls = []

    def post(self, url, headers=None, json=None, timeout=None, **kwargs):
        self.urls.append(url)
        if ":generateContent" in url:
            reply = {"score": self.score, "reason": "pricing material"}
            return FakeResponse(200, {
                "candidates": [{"content": {"parts": [{"text": _dumps(reply)}]}}],
                "usageMetadata": {"promptTokenCount": 850, "candidatesTokenCount": 20, "thoughtsTokenCount": 30},
            })
        if ":batchEmbedContents" in url:
            return FakeResponse(200, {"embeddings": [{"values": [1.0, 0.0, 0.0, 0.0]} for _ in json["requests"]]})
        if "openrouter.ai" in url:
            system = json["messages"][0]["content"]
            if "catalog search analyzer" in system:
                content, usage = {"expanded_terms": ["headset", "studio monitor"]}, (120, 15)
            elif "catalog specialist" in system:
                content = {"keywords": ["studio headphones"], "use_cases": ["mixing"], "target_industries": ["Media"],
                           "value_proposition": "Accurate monitoring.", "ideal_customer_profile": "Studios.",
                           "min_discount_pct": 5.0, "max_discount_pct": 20.0}
                usage = (600, 200)
            else:
                content, usage = CLASSIFICATION, (1000, 90)
            return FakeResponse(200, {
                "model": SERVED_MODEL,
                "usage": {"prompt_tokens": usage[0], "completion_tokens": usage[1]},
                "choices": [{"message": {"content": _dumps(content)}, "finish_reason": "stop"}],
            })
        raise AssertionError(f"unexpected provider call to {url}")


def _dumps(value):
    return json.dumps(value)


class FakeLlamaParse:
    split_by_page = True
    page_separator = None

    def __init__(self, pages):
        self.pages = pages
        self.calls = 0

    def load_data(self, path):
        self.calls += 1
        return [SimpleNamespace(text=text, metadata={}) for text in self.pages]


class EmbeddingOnlyPipeline:
    """The ingestion pipeline without vector storage: chunks the text and embeds it with the real worker."""

    def __init__(self, embedding_worker):
        self.worker = embedding_worker

    def process_document(self, document):
        text = document.text_content
        pieces = [text[i:i + 120] for i in range(0, len(text), 120)]
        nodes = [
            TextNode(chunk_id=f"{document.doc_id}_{i}", doc_id=document.doc_id, tenant_id=document.tenant_id,
                     user_id=document.user_id, source=document.source, external_id=document.external_id, text=piece,
                     chunk_hash=f"h{i}", acl=list(document.acl), chunk_index=i, total_chunks=len(pieces))
            for i, piece in enumerate(pieces)
        ]
        return len(self.worker.generate_embeddings(nodes))


@pytest.fixture
def providers(monkeypatch):
    fake = Providers()
    monkeypatch.setattr(requests, "post", fake.post)
    for name, value in {
        "GEMINI_API_KEY": "test-key", "OPEN_ROUTER_API": "sk-or-test", "EMBEDDING_MODEL": EMBEDDING_MODEL,
        "EMBEDDING_DIMENSIONS": "4", "GATEKEEPER_SEMANTIC_ENABLED": "true",
    }.items():
        monkeypatch.setenv(name, value)
    for name in ("GOOGLE_GEMINI_MODE", "OPENROUTER_MODEL", "OPENROUTER_FALLBACK_MODELS", "OPENROUTER_API_KEY"):
        monkeypatch.delenv(name, raising=False)
    return fake


@pytest.fixture
def vault(monkeypatch, providers, billing):
    monkeypatch.setattr(
        workspace_access, "directory", MembershipDirectory("http://workspace.test", fetch=lambda base, user, t: ROLES.get(user, {}))
    )
    llama = FakeLlamaParse(PAGES)
    monkeypatch.setattr(kv.parser_service.llama_parser, "parser", llama)
    monkeypatch.setattr(kv, "BatchIngestionPipeline", EmbeddingOnlyPipeline)
    kv._in_memory_docs.clear()
    app = FastAPI()
    app.include_router(kv.router, prefix="/api/v1")
    yield SimpleNamespace(client=TestClient(app), llama=llama, billing=billing, providers=providers)
    kv._in_memory_docs.clear()


def upload(client, name="pricing.pdf", body=PDF_BYTES, mime="application/pdf", user=MEMBER):
    response = client.post(
        "/api/v1/knowledge-vault/upload",
        headers={"X-User-Id": user, "X-Tenant-Id": WORKSPACE},
        files={"file": (name, body, mime)},
    )
    assert response.status_code == 200, response.text
    return response.json()


def run_queued_jobs():
    """Run what was queued the way the worker does: the parse stage, then the embedding stage."""
    handlers = {JOB_DOCUMENT_INGEST: kv.process_document_job, JOB_DOCUMENT_EMBED: kv.process_embed_job}
    ran = []
    while (job := ingest_queue.reserve()) is not None:
        handlers[job.kind](job.payload)
        ingest_queue.ack(job)
        ran.append(job.kind)
    return ran


def scorer_item():
    return {"type": "TOKENS", "model": DEFAULT_SEMANTIC_MODEL, "inputTokens": 850, "cachedInputTokens": 0, "outputTokens": 50}


def classifier_item():
    return {"type": "TOKENS", "model": SERVED_MODEL, "inputTokens": 1000, "cachedInputTokens": 0, "outputTokens": 90}


# =========================================================================
# document.ingest - knowledge vault
# =========================================================================
def test_an_uploaded_pdf_is_charged_once_for_parsing_scoring_classifying_and_embedding(vault):
    doc_id = upload(vault.client)["document"]["doc_id"]

    assert run_queued_jobs() == [JOB_DOCUMENT_INGEST, JOB_DOCUMENT_EMBED]

    assert kv._in_memory_docs[doc_id]["status"] == "Indexed"
    [charge] = vault.billing.charges  # one report for the whole document
    assert (charge["operation"], charge["category"]) == ("document.ingest", "DOCUMENTS")
    assert (charge["workspaceId"], charge["userId"], charge["reference"]) == (WORKSPACE, MEMBER, doc_id)
    assert charge["idempotencyKey"].startswith(f"document.ingest:{doc_id}:")
    tokens, units = items_by_kind(charge)
    assert units == {"LLAMAPARSE_PAGE": 3}
    assert tokens[DEFAULT_SEMANTIC_MODEL] == scorer_item()
    assert tokens[SERVED_MODEL] == classifier_item()
    # Estimated from the characters sent: every chunk went in one batchEmbedContents call.
    assert tokens[EMBEDDING_MODEL]["inputTokens"] == estimate_tokens(len(PARSED_TEXT))
    assert charge["metadata"]["stage"] == "index"


def test_retrying_either_stage_never_charges_twice(vault, monkeypatch):
    doc_id = upload(vault.client)["document"]["doc_id"]
    save = kv.raw_document_store.save_raw_document
    attempts = []

    def fails_once(**kwargs):  # after LlamaParse, the scorer and the classifier already ran
        attempts.append(1)
        if len(attempts) == 1:
            raise RuntimeError("MongoDB went away")
        return save(**kwargs)

    monkeypatch.setattr(kv.raw_document_store, "save_raw_document", fails_once)
    job = ingest_queue.reserve()
    with pytest.raises(RuntimeError):
        kv.process_document_job(job.payload)
    assert vault.billing.charges == []  # a failed attempt is not charged

    kv.process_document_job(job.payload)  # the queue's retry, same payload
    embed = ingest_queue.reserve()
    kv.process_embed_job(embed.payload)
    kv.process_embed_job(embed.payload)  # embedding redelivered

    [billed] = vault.billing.of("document.ingest")
    assert len(vault.billing.charges) == 2  # reported twice, charged once
    assert items_by_kind(billed)[1] == {"LLAMAPARSE_PAGE": 3}
    assert billed["reference"] == doc_id


def test_re_uploading_an_indexed_file_is_free_but_a_reindex_is_charged_again(vault):
    doc_id = upload(vault.client)["document"]["doc_id"]
    run_queued_jobs()

    assert upload(vault.client)["status"] == "duplicate"
    assert run_queued_jobs() == []
    assert len(vault.billing.of("document.ingest")) == 1

    reindexed = vault.client.post(f"/api/v1/knowledge-vault/documents/{doc_id}/reindex", headers=HEADERS)
    assert reindexed.status_code == 200, reindexed.text
    run_queued_jobs()

    first, second = vault.billing.of("document.ingest")
    assert first["idempotencyKey"] != second["idempotencyKey"]
    assert items_by_kind(second)[1] == {"LLAMAPARSE_PAGE": 3}
    assert vault.llama.calls == 2


def test_a_text_file_is_charged_without_any_parsed_pages(vault):
    upload(vault.client, "battlecard.md", b"# Globex battlecard\n" + PARSED_TEXT.encode(), "text/markdown")

    run_queued_jobs()

    [charge] = vault.billing.of("document.ingest")
    tokens, units = items_by_kind(charge)
    assert units == {}
    assert vault.llama.calls == 0
    assert set(tokens) == {DEFAULT_SEMANTIC_MODEL, SERVED_MODEL, EMBEDDING_MODEL}


def test_a_document_the_gatekeeper_holds_is_charged_for_what_it_spent_before_the_hold(vault, monkeypatch):
    monkeypatch.setenv("GATEKEEPER_SEMANTIC_ENFORCED", "true")
    vault.providers.score = 0.05
    doc_id = upload(vault.client)["document"]["doc_id"]

    assert run_queued_jobs() == [JOB_DOCUMENT_INGEST]

    assert kv._in_memory_docs[doc_id]["status"] == "Rejected"
    [charge] = vault.billing.charges
    tokens, units = items_by_kind(charge)
    assert units == {"LLAMAPARSE_PAGE": 3}
    assert list(tokens.values()) == [scorer_item()]  # never classified or embedded
    assert charge["metadata"]["stage"] == "held"


def test_work_without_a_workspace_is_not_charged(vault):
    kv.raw_document_store.save_raw_document(
        doc_ref_id="doc_legacy", tenant_id="tenant_default", user_id="legacy_user", filename="old.md",
        mime_type="text/markdown", full_text_content=PARSED_TEXT,
    )

    kv.process_embed_job({
        "doc_id": "doc_legacy", "tenant_id": "tenant_default", "user_id": "legacy_user", "source": "USER_UPLOAD",
        "acl": [], "text_ref": "doc_legacy",
    })

    assert kv.raw_document_store.get_full_text("doc_legacy") == PARSED_TEXT  # it was embedded...
    assert vault.billing.charges == []  # ...but there is no workspace to charge


# =========================================================================
# document.ingest - synced connector documents
# =========================================================================
def synced_email(rep=REP):
    received = datetime(2026, 9, 14, 9, 30, tzinfo=timezone.utc)
    return CanonicalEvent(
        event_id=f"gmail_{WORKSPACE}_msg_1", event_type=EventType.CREATE, source="gmail", tenant_id=WORKSPACE,
        user_id=rep, external_id="msg_1", raw_ref={"message_id": "msg_1"}, acl=["rep@acme.test"], timestamp=received,
        metadata={
            "subject": "Globex quote", "sender": "buyer@globex.test", "to": "rep@acme.test", "received_at": received.isoformat(),
            "body": "Please find the pricing attached. We need approval for the multi-year discount band.",
            "name": "Email: Globex quote", "mime_type": "message/rfc822",
            "attachments": [{"filename": "quote.pdf", "mime_type": "application/pdf", "size_bytes": len(PDF_BYTES), "raw_bytes": PDF_BYTES}],
        },
    )


def connector_worker(pages):
    worker = QueueWorker(queue=ingest_queue)
    worker.parser_service.llama_parser.parser = FakeLlamaParse(pages)
    return worker


def test_a_synced_email_is_charged_once_as_connectors_however_often_it_arrives(vault):
    worker = connector_worker(PAGES[:2])

    asyncio.run(worker._process_event(synced_email()))
    run_queued_jobs()
    asyncio.run(worker._process_event(synced_email()))  # a webhook redelivery or a resync of the same email
    run_queued_jobs()

    [charge] = vault.billing.of("document.ingest")
    assert (charge["category"], charge["workspaceId"], charge["userId"]) == ("CONNECTORS", WORKSPACE, REP)
    assert charge["reference"] == f"{WORKSPACE}:gmail:{REP}:msg_1"
    tokens, units = items_by_kind(charge)
    assert units == {"LLAMAPARSE_PAGE": 2}  # the attachment's pages
    assert tokens[SERVED_MODEL] == classifier_item()
    assert set(tokens) == {DEFAULT_SEMANTIC_MODEL, SERVED_MODEL, EMBEDDING_MODEL}


class FakeTools:
    """Composio's tools for Drive: one file to list, downloadable as base64 content."""

    def __init__(self):
        self.executed = []

    def execute(self, slug, arguments, user_id=None, dangerously_skip_version_check=None):
        self.executed.append(slug)
        if slug == "GOOGLEDRIVE_LIST_FILES":
            return {"data": {"files": [{"id": "file_1", "name": "pricing.pdf", "mimeType": "application/pdf", "size": 2048}]}}
        if slug == "GOOGLEDRIVE_DOWNLOAD_FILE":
            return {"data": {"content": base64.b64encode(PDF_BYTES).decode()}}
        raise AssertionError(f"unexpected tool {slug}")


def test_a_drive_sync_charges_its_composio_executions_once_and_each_file_it_ingested(vault, monkeypatch):
    monkeypatch.setattr(gdrive_module, "global_rate_limiter", SimpleNamespace(acquire=lambda provider: asyncio.sleep(0)))
    tools = FakeTools()
    composio = SimpleNamespace(_composio=SimpleNamespace(tools=tools), is_account_connected=lambda **kwargs: True)
    store = GDriveStore()
    conn = store.get_or_create_connection(tenant_id=WORKSPACE, user_id=REP)
    manager = GDriveSyncManager(composio_client=composio, store=store, queue_worker=connector_worker(PAGES + ["Appendix"]))

    asyncio.run(manager.start_sync_job(conn.connection_id, trigger_type=GDriveTriggerType.MANUAL_SYNC))
    run_queued_jobs()

    [sync] = vault.billing.of("connector.sync")
    assert (sync["category"], sync["workspaceId"], sync["userId"]) == ("CONNECTORS", WORKSPACE, REP)
    assert sync["items"] == [{"type": "UNITS", "unit": "COMPOSIO_EXECUTION", "quantity": len(tools.executed)}]
    assert tools.executed == ["GOOGLEDRIVE_LIST_FILES", "GOOGLEDRIVE_DOWNLOAD_FILE"]
    assert sync["metadata"] == {"source": "gdrive", "trigger": "MANUAL_SYNC"}

    [ingest] = vault.billing.of("document.ingest")
    assert ingest["category"] == "CONNECTORS"
    # The file was parsed while it was downloaded; those pages are charged with the file.
    assert items_by_kind(ingest)[1] == {"LLAMAPARSE_PAGE": 4}


def test_a_sync_run_reports_its_executions_once_even_when_it_fails(billing):
    class Manager:
        store = SimpleNamespace(_connections={"conn_1": SimpleNamespace(tenant_id=WORKSPACE, user_id=REP)})

        @metered_sync_run("notion")
        async def execute_sync_job(self, connection_id, trigger_type=None, is_resync=False):
            record_composio_execution()
            record_composio_execution()
            raise RuntimeError("Notion API is down")

        @metered_sync_run("notion")
        async def idle_job(self, connection_id, trigger_type=None):
            return None

    with pytest.raises(RuntimeError):
        asyncio.run(Manager().execute_sync_job("conn_1", trigger_type=SimpleNamespace(value="AUTO_SYNC")))
    asyncio.run(Manager().idle_job("conn_1"))

    [charge] = billing.charges  # a run that made no calls reports nothing
    assert charge["operation"] == "connector.sync" and charge["reference"] == "conn_1"
    assert charge["items"] == [{"type": "UNITS", "unit": "COMPOSIO_EXECUTION", "quantity": 2}]
    assert charge["metadata"]["trigger"] == "AUTO_SYNC"


# =========================================================================
# document.reclassify, knowledge.search, catalog.ai
# =========================================================================
def test_reclassifying_a_document_is_charged_for_the_classifier(vault):
    doc_id = "doc_reclass01"
    kv._in_memory_docs[doc_id] = {
        "doc_id": doc_id, "name": "pricing.md", "tenant_id": WORKSPACE, "user_id": MEMBER, "source": "USER_UPLOAD",
        "status": "Indexed", "chunks": 2, "metadata": {"preview_snippet": PARSED_TEXT},
    }

    response = vault.client.post(f"/api/v1/knowledge-vault/documents/{doc_id}/reclassify", headers=HEADERS)

    assert response.status_code == 200, response.text
    [charge] = vault.billing.charges
    assert (charge["operation"], charge["category"], charge["reference"], charge["userId"]) == (
        "document.reclassify", "DOCUMENTS", doc_id, MEMBER,
    )
    assert charge["items"] == [classifier_item()]


def test_a_knowledge_search_is_charged_for_its_query_embedding(vault, monkeypatch):
    monkeypatch.setattr(kv, "query_embedder", EmbeddingWorker())
    monkeypatch.setattr(kv.vector_store, "search_similarity", lambda **kwargs: [])
    query = "who wins against Globex on price?"

    response = vault.client.post("/api/v1/knowledge-vault/search", headers=HEADERS, json={"query": query})

    assert response.status_code == 200, response.text
    [charge] = vault.billing.charges
    assert (charge["operation"], charge["category"], charge["userId"]) == ("knowledge.search", "SEARCH", MEMBER)
    assert charge["items"] == [
        {"type": "TOKENS", "model": EMBEDDING_MODEL, "inputTokens": estimate_tokens(len(query)), "cachedInputTokens": 0, "outputTokens": 0}
    ]


class _SearchWithoutDatabase(ProductService):
    def semantic_search(self, tenant_id, query, limit=20, expand=True):
        return SemanticSearchResponse(query=query, expanded_terms=self._expand_query(query), results=[])


def test_catalog_ai_is_charged_for_findability_and_query_expansion(providers, billing):
    app = FastAPI()
    app.include_router(catalog_router, prefix="/api/v1/catalog")
    app.dependency_overrides[get_catalog_context] = lambda: CatalogContext(UUID(WORKSPACE), MEMBER, "MEMBER")
    app.dependency_overrides[get_service] = lambda: _SearchWithoutDatabase(db=None)
    client = TestClient(app)
    findability = {
        "name": "Studio Headphones Pro", "type": "PRODUCT", "category": "audio",
        "description": "High-fidelity closed-back headphones engineered for studio monitoring, mixing and critical listening, "
                       "with 50mm neodymium drivers, a wide 10Hz to 35kHz frequency response, a detachable cable and memory foam earcups.",
    }

    assert client.post("/api/v1/catalog/ai/generate-findability", headers=HEADERS, json=findability).status_code == 200
    searched = client.post("/api/v1/catalog/ai/semantic-search", headers=HEADERS, json={"query": "headphones for mixing"})
    assert searched.status_code == 200 and searched.json()["expanded_terms"] == ["headset", "studio monitor"]

    generated, expanded = billing.of("catalog.ai")
    assert (generated["category"], generated["workspaceId"], generated["metadata"]["feature"]) == ("CATALOG", WORKSPACE, "findability")
    assert generated["items"] == [{"type": "TOKENS", "model": SERVED_MODEL, "inputTokens": 600, "cachedInputTokens": 0, "outputTokens": 200}]
    assert expanded["metadata"]["feature"] == "query_expansion"
    assert expanded["items"] == [{"type": "TOKENS", "model": SERVED_MODEL, "inputTokens": 120, "cachedInputTokens": 0, "outputTokens": 15}]


# =========================================================================
# Background work skips a workspace that may not spend
# =========================================================================
@pytest.mark.parametrize("allowed", [True, False], ids=["allowed", "refused"])
@pytest.mark.parametrize("manager_class, loop, running_flag, sync_job", SCHEDULERS)
def test_scheduled_syncs_skip_a_workspace_that_may_not_spend(monkeypatch, billing, manager_class, loop, running_flag, sync_job, allowed):
    import sys

    connection = _due_connection(WORKSPACE)
    manager = manager_class.__new__(manager_class)
    manager.store = _Store([connection])
    manager.composio = SimpleNamespace(is_account_connected=lambda user_id, source: True)
    manager._last_auto_sync_times = {}
    setattr(manager, running_flag, True)
    started = []

    async def record_sync(connection_id, **options):
        started.append(connection_id)

    setattr(manager, sync_job, record_sync)
    passes = []

    async def one_pass(seconds):
        passes.append(seconds)
        if len(passes) > 1:
            raise asyncio.CancelledError

    monkeypatch.setattr(
        sys.modules[manager_class.__module__], "asyncio",
        SimpleNamespace(sleep=one_pass, create_task=asyncio.create_task, CancelledError=asyncio.CancelledError),
    )
    if not allowed:
        billing.deny()

    async def run():
        await getattr(manager, loop)()
        await asyncio.gather(*[task for task in asyncio.all_tasks() if task is not asyncio.current_task()])

    asyncio.run(run())

    assert started == ([connection.connection_id] if allowed else [])
    assert billing.checks == [(WORKSPACE, connection.user_id)]


def _webhook_managers():
    worker = _Worker()

    gmail_store = GmailStore()
    gmail = GmailSyncManager(store=gmail_store, composio=SimpleNamespace(), queue_worker=worker)
    gmail_conn = gmail_store.get_or_create_connection(tenant_id=WORKSPACE, user_id=REP)

    drive_store = GDriveStore()
    drive = GDriveSyncManager(composio_client=SimpleNamespace(_composio=None), store=drive_store, queue_worker=worker)
    drive_conn = drive_store.get_or_create_connection(tenant_id=WORKSPACE, user_id=REP)

    calendar_store = CalendarStore()
    calendar = CalendarSyncManager(composio_client=SimpleNamespace(_composio=None), store=calendar_store, queue_worker=worker)
    calendar_conn = calendar_store.get_or_create_connection(tenant_id=WORKSPACE, user_id=REP)

    slack_store, notion_store = SlackStore(), NotionStore()
    slack = SlackSyncManager(store=slack_store, composio=SimpleNamespace(), queue_worker=worker)
    notion = NotionSyncManager(store=notion_store, composio=SimpleNamespace(), queue_worker=worker)

    for store, conn in ((gmail_store, gmail_conn), (drive_store, drive_conn), (calendar_store, calendar_conn)):
        conn.config.webhook_enabled = True
        store.update_connection(conn)
    return worker, [
        ("gmail", lambda event: gmail.process_webhook_event(event)),
        ("gdrive", lambda event: drive.process_webhook_event(event, raw_payload={}, connection=drive_conn)),
        ("google_calendar", lambda event: calendar.process_webhook_event(event, raw_payload={})),
        ("slack", lambda event: slack.process_webhook_event(event, connection=slack_store.get_or_create_connection(WORKSPACE, REP))),
        ("notion", lambda event: notion.process_webhook_event(event, connection=notion_store.get_or_create_connection(WORKSPACE, REP))),
    ]


def test_webhook_ingestion_is_skipped_for_a_workspace_that_may_not_spend(billing):
    billing.deny("CREDITS_SUSPENDED")
    worker, handlers = _webhook_managers()

    for source, handle in handlers:
        event = CanonicalEvent(
            event_id=f"{source}_{WORKSPACE}_sim_1", event_type=EventType.CREATE, source=source, tenant_id=WORKSPACE,
            user_id=REP, external_id="sim_1", raw_ref={}, acl=[REP],
            metadata={"name": "Pricing notes", "title": "Pricing notes", "summary": "Pricing call", "text": "Globex wants a 12-month term."},
        )
        result = asyncio.run(handle(event))
        assert (result["status"], result["code"]) == ("skipped", "CREDITS_SUSPENDED"), (source, result)

    assert worker.events == []
    assert billing.charges == []


def test_scheduled_reconciliation_skips_a_workspace_that_may_not_spend(monkeypatch, billing):
    listed = []

    class Lister:
        def __init__(self, composio):
            pass

        def list_source(self, source, user_id):
            listed.append(user_id)
            return SimpleNamespace(complete=True, items=[], reason="")

    monkeypatch.setattr(scheduler_module, "LiveSourceLister", Lister)
    scheduler = ReconciliationScheduler(
        providers={"gdrive": SimpleNamespace(store=_Store([_due_connection(WORKSPACE)]), composio=None)},
        sweeper=SimpleNamespace(sweep_source=lambda **kwargs: SimpleNamespace(**kwargs)),
    )
    billing.deny()

    assert scheduler.sweep_all() == []
    assert listed == []
