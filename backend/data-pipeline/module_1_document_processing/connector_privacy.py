"""Documents synced from a rep's connected apps are private to that rep.

Decided 2026-09-15: what a rep syncs from Gmail, Google Calendar, Slack (direct and group messages included),
Google Drive and Notion belongs to them. Only they, and their own agent acting for them, can list, read, search,
change or delete it; nobody else in the workspace can, owners and admins included. Everything else in the
knowledge vault (uploaded files, web pages, catalog documents) stays shared with the workspace.

Two rules enforce it:
- ``visible_to``: a registry row from a connector source is visible only to the rep who synced it. Every
  knowledge-vault route and the gatekeeper's holds apply it.
- ``chunk_acl``: a connector document's chunks are indexed without the workspace's ``tenant:`` entry and always
  with the rep's ``user:`` entry. Search matches a caller's ``tenant:`` and ``user:`` entries, so only that rep
  finds them.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

# Every spelling a connector source is stored under: canonical events and chunks use lower-case names, vault
# registry rows upper-case them, and the connector routes accept the aliases.
CONNECTOR_SOURCES = frozenset(
    {"gmail", "gdrive", "googledrive", "google_drive", "google_calendar", "googlecalendar", "calendar", "slack", "notion"}
)


def is_connector_source(source: Any) -> bool:
    return isinstance(source, str) and source.strip().lower() in CONNECTOR_SOURCES


def document_id(tenant_id: str, source: str, user_id: str, external_id: str) -> str:
    """The pipeline's id for a document, which keys its lineage, text, chunks, gatekeeper hold and registry row.

    A connector document's id names the rep it was synced for (``tenant:source:user:external_id``), so two reps
    who sync the same message, file or event each get their own private copy instead of one overwriting the
    other's. Any other document keeps ``tenant:source:external_id``. The user comes before the provider's id,
    which may itself contain ``:`` (a Slack message is ``channel:ts``)."""
    if not is_connector_source(source):
        return f"{tenant_id}:{source}:{external_id}"
    if not user_id:
        raise ValueError(f"a {source} document needs the rep it was synced for")
    return f"{tenant_id}:{source}:{user_id}:{external_id}"


def visible_to(record: Mapping[str, Any] | None, user_id: str) -> bool:
    """Whether ``user_id``, a member of the record's workspace, may see this registry row (or held document)."""
    if not record:
        return False
    if not is_connector_source(record.get("source")):
        return True
    return bool(user_id) and str(record.get("user_id") or "") == str(user_id)


def shared_records_filter() -> dict[str, Any]:
    """The MongoDB condition for registry rows that are not synced from anyone's apps."""
    return {"source": {"$nin": sorted({spelling for name in CONNECTOR_SOURCES for spelling in (name, name.upper())})}}


def visible_records_filter(user_id: str) -> dict[str, Any]:
    """The MongoDB condition for the registry rows ``user_id`` may see (combine it with the workspace filter)."""
    return {"$or": [shared_records_filter(), {"user_id": user_id}]}


def chunk_acl(source: Any, user_id: str, acl: Iterable[Any]) -> list[str]:
    """The ACL a document's chunks are indexed with. A connector document never carries a ``tenant:`` entry and
    always carries its rep's ``user:`` entry; any other document keeps its ACL as it is."""
    entries = [str(entry) for entry in acl]
    if not is_connector_source(source):
        return entries
    kept = [entry for entry in entries if not entry.startswith("tenant:")]
    owner = f"user:{user_id}"
    if user_id and owner not in kept:
        kept.append(owner)
    return kept
