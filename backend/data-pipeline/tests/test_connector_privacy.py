"""Documents synced from a rep's connected apps are private to that rep.

Nobody else in the workspace, owners and admins included, can list, read, change, delete or find them, while
uploaded documents stay shared. Runs the real knowledge-vault and gatekeeper routes with MongoDB unreachable
(in-memory stores) and workspace-service faked, plus the embedding step, permission sync, reconciliation and
webhook attribution on their in-memory stores.
"""

import asyncio
import os
import uuid
from datetime import datetime, timezone
from types import SimpleNamespace

os.environ.setdefault("MONGODB_URI", "mongodb://127.0.0.1:1")  # force the in-memory stores

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from module_1_document_processing import connector_privacy, knowledge_vault_routes, workspace_access
from module_1_document_processing.composio_connector.calendar_store import CalendarStore
from module_1_document_processing.composio_connector.calendar_sync_manager import CalendarSyncManager
from module_1_document_processing.composio_connector.events.canonical_event import CanonicalEvent, EventType
from module_1_document_processing.composio_connector.gdrive_store import GDriveStore
from module_1_document_processing.composio_connector.gdrive_sync_manager import GDriveSyncManager
from module_1_document_processing.composio_connector.notion_store import NotionStore
from module_1_document_processing.composio_connector.notion_sync_manager import NotionSyncManager
from module_1_document_processing.composio_connector.slack_store import SlackStore
from module_1_document_processing.composio_connector.slack_sync_manager import SlackSyncManager
from module_1_document_processing.del_acl_and_reconc.acl_sync import ACLSyncService
from module_1_document_processing.del_acl_and_reconc.deletion_handler import DeletionHandler
from module_1_document_processing.del_acl_and_reconc.reconciliation_sweeper import ReconciliationSweeper
from module_1_document_processing.pipeline.canonical_store import CanonicalStore
from module_1_document_processing.raw_document_store import raw_document_store
from module_1_document_processing.workspace_access import MembershipDirectory
from module_2_memory_gatekeeper import gatekeeper_routes
from module_2_memory_gatekeeper.gatekeeper_store import KIND_REJECTED, GatekeeperStore
from module_1_document_processing.parsing.parsed_document import ParsedDocument

WORKSPACE = str(uuid.uuid4())
OTHER_WORKSPACE = str(uuid.uuid4())
OWNER, REP, TEAMMATE, VIEWER = (str(uuid.uuid4()) for _ in range(4))
ROLES = {
    OWNER: {WORKSPACE: "OWNER"},
    REP: {WORKSPACE: "MEMBER"},
    TEAMMATE: {WORKSPACE: "MEMBER"},
    VIEWER: {WORKSPACE: "VIEWER"},
}


def _as(user, workspace=WORKSPACE):
    return {"X-User-Id": user, "X-Tenant-Id": workspace}


@pytest.fixture
def members(monkeypatch):
    monkeypatch.setattr(
        workspace_access, "directory", MembershipDirectory("http://workspace.test", fetch=lambda base, user, t: ROLES.get(user, {}))
    )


@pytest.fixture
def vault(members, monkeypatch):
    monkeypatch.setattr(knowledge_vault_routes, "_process_document_background", lambda **kwargs: None)
    monkeypatch.setattr(knowledge_vault_routes, "_queue_document_job", lambda *args, **kwargs: None)
    knowledge_vault_routes._in_memory_docs.clear()
    app = FastAPI()
    app.include_router(knowledge_vault_routes.router, prefix="/api/v1")
    return TestClient(app)


def _registry_row(doc_id, user, source, name, size=120):
    now = datetime.now(timezone.utc).isoformat()
    knowledge_vault_routes._save_doc_record({
        "doc_id": doc_id, "doc_ref_id": doc_id, "name": name, "type": source, "source": source,
        "tenant_id": WORKSPACE, "user_id": user, "status": "Indexed", "chunks": 1, "size_bytes": size,
        "category": "GENERAL_RESOURCE", "sales_tags": [], "created_at": now, "last_updated": now,
        "metadata": {"preview_snippet": f"{name} preview"},
    })
    raw_document_store.save_raw_document(
        doc_ref_id=doc_id, tenant_id=WORKSPACE, user_id=user, filename=name, mime_type="text/plain",
        full_text_content=f"Full text of {name}",
    )
    return doc_id


def _synced_email(user, name="Re: Acme renewal pricing"):
    return _registry_row(f"{WORKSPACE}:gmail:{user}:{uuid.uuid4().hex[:12]}", user, "GMAIL", name)


def _upload(user, name="Globex battlecard.md"):
    return _registry_row(f"doc_{uuid.uuid4().hex[:12]}", user, "USER_UPLOAD", name)


# --------------------------------------------------------------------------- the rules


def test_the_rules_separate_synced_documents_from_shared_ones():
    email = {"source": "GMAIL", "user_id": REP}
    assert connector_privacy.visible_to(email, REP)
    assert not connector_privacy.visible_to(email, OWNER)
    assert not connector_privacy.visible_to({"source": "gmail", "user_id": ""}, "")  # no owner: nobody
    assert connector_privacy.visible_to({"source": "USER_UPLOAD", "user_id": REP}, TEAMMATE)
    assert connector_privacy.visible_to({"user_id": REP}, TEAMMATE)  # rows from before sources were recorded
    assert not connector_privacy.visible_to(None, REP)

    for source in ("gmail", "GDRIVE", "google_calendar", "slack", "Notion"):
        assert connector_privacy.chunk_acl(source, REP, [f"tenant:{WORKSPACE}", "rohan@acme.test"]) == ["rohan@acme.test", f"user:{REP}"]
    assert connector_privacy.chunk_acl("slack", REP, [f"user:{REP}", "channel:C1"]) == [f"user:{REP}", "channel:C1"]
    shared = [f"user:{REP}", f"tenant:{WORKSPACE}"]
    assert connector_privacy.chunk_acl("USER_UPLOAD", REP, shared) == shared


def test_a_synced_documents_id_names_its_rep_and_an_uploads_does_not():
    assert connector_privacy.document_id(WORKSPACE, "slack", REP, "C1:1712.5") == f"{WORKSPACE}:slack:{REP}:C1:1712.5"
    assert connector_privacy.document_id(WORKSPACE, "USER_UPLOAD", REP, "doc_1") == f"{WORKSPACE}:USER_UPLOAD:doc_1"
    with pytest.raises(ValueError):
        connector_privacy.document_id(WORKSPACE, "gmail", "", "msg_1")


def test_two_reps_syncing_the_same_file_each_get_their_own_copy():
    store = CanonicalStore(use_db=False)
    handler = DeletionHandler(store, vector_store=SimpleNamespace(delete_by_doc_id=lambda doc_id: 0))
    store.record_event(_event("gdrive", REP, "shared_deck"), status="VECTOR_STORE_INDEXED")
    store.record_event(_event("gdrive", TEAMMATE, "shared_deck"), status="VECTOR_STORE_INDEXED")

    copies = {doc.user_id: doc.doc_id for doc in store.list_documents(WORKSPACE, "gdrive", exclude_statuses=())}
    assert copies == {REP: f"{WORKSPACE}:gdrive:{REP}:shared_deck", TEAMMATE: f"{WORKSPACE}:gdrive:{TEAMMATE}:shared_deck"}

    handler.process_deletion(_event("gdrive", REP, "shared_deck", kind=EventType.DELETE))  # the rep's copy is gone

    assert store.get_document(copies[REP]).status == "DELETED"
    assert store.get_document(copies[TEAMMATE]).status == "VECTOR_STORE_INDEXED"


# --------------------------------------------------------------------------- knowledge vault routes


def test_a_reps_synced_documents_are_listed_and_counted_only_for_them(vault):
    email = _synced_email(REP)
    battlecard = _upload(OWNER)

    def listed(user, query=""):
        return {d["doc_id"] for d in vault.get(f"/api/v1/knowledge-vault/documents{query}", headers=_as(user)).json()["documents"]}

    assert listed(REP) == {email, battlecard}
    assert listed(REP, "?mine=true") == {email}
    assert listed(OWNER) == listed(TEAMMATE) == listed(VIEWER) == {battlecard}
    assert listed(OWNER, "?search=renewal") == set()
    assert vault.get("/api/v1/knowledge-vault/stats", headers=_as(REP)).json()["stats"]["total_documents"] == 2
    assert vault.get("/api/v1/knowledge-vault/stats", headers=_as(OWNER)).json()["stats"]["total_documents"] == 1


def test_nobody_else_can_read_change_or_delete_a_synced_document(vault):
    email = _synced_email(REP)

    for user in (OWNER, TEAMMATE, VIEWER):
        for method, path, body in (
            ("GET", f"/documents/{email}/content", None),
            ("GET", f"/documents/{email}/vectors", None),
            ("GET", f"/documents/{email}/download", None),
            ("PATCH", f"/documents/{email}/sales-classification", {"category": "BATTLECARD"}),
            ("POST", f"/documents/{email}/reclassify", None),
            ("POST", f"/documents/{email}/reindex", None),
            ("DELETE", f"/documents/{email}", None),
        ):
            answer = vault.request(method, f"/api/v1/knowledge-vault{path}", headers=_as(user), json=body)
            assert answer.status_code in (403, 404), (user, method, path, answer.status_code)
            if user != VIEWER:  # a viewer is refused writes before the lookup; members and owners never find it
                assert answer.status_code == 404, (user, method, path, answer.text)

    assert knowledge_vault_routes._find_doc_record(email) is not None  # still there
    content = vault.get(f"/api/v1/knowledge-vault/documents/{email}/content", headers=_as(REP))
    assert content.status_code == 200 and "Full text of Re: Acme renewal pricing" in content.text


def test_duplicate_cleanup_leaves_synced_documents_alone(vault):
    _synced_email(REP, name="Weekly pipeline review")
    _synced_email(TEAMMATE, name="Weekly pipeline review")  # the same meeting email in two mailboxes
    _upload(REP, name="Pricing.pdf")
    _upload(TEAMMATE, name="Pricing.pdf")

    plan = vault.post("/api/v1/knowledge-vault/deduplicate", headers=_as(OWNER))

    assert plan.status_code == 200
    assert [group["name"] for group in plan.json()["details"]] == ["Pricing.pdf"]
    assert "Weekly pipeline review" not in plan.text


def test_reindexing_a_synced_document_embeds_its_stored_text_again_for_its_rep(vault, monkeypatch):
    email = _synced_email(REP)
    queued = []
    monkeypatch.setattr(knowledge_vault_routes.ingest_queue, "enqueue", lambda kind, payload: queued.append((kind, payload)))

    def no_upload_path(*args, **kwargs):
        raise AssertionError("a synced document isn't parsed or classified again")

    monkeypatch.setattr(knowledge_vault_routes, "_queue_document_job", no_upload_path)

    answer = vault.post(f"/api/v1/knowledge-vault/documents/{email}/reindex", headers=_as(REP))

    assert answer.status_code == 200, answer.text
    [(kind, payload)] = queued
    assert kind == knowledge_vault_routes.JOB_DOCUMENT_EMBED
    assert (payload["doc_id"], payload["canonical_doc_id"], payload["user_id"], payload["source"]) == (email, email, REP, "gmail")
    assert not any(entry.startswith("tenant:") for entry in payload["acl"]) and f"user:{REP}" in payload["acl"]


# --------------------------------------------------------------------------- indexing and permissions


def test_embedding_indexes_a_synced_document_for_its_rep_only(monkeypatch):
    indexed = []

    class Pipeline:
        def __init__(self, embedding_worker):
            pass

        def process_document(self, document):
            indexed.append(document)
            return 1

    monkeypatch.setattr(knowledge_vault_routes, "EmbeddingWorker", lambda model_name=None: None)
    monkeypatch.setattr(knowledge_vault_routes, "BatchIngestionPipeline", Pipeline)
    monkeypatch.setattr(knowledge_vault_routes.raw_document_store, "get_full_text", lambda ref: "Body")
    monkeypatch.setattr(knowledge_vault_routes.raw_document_store, "update_chunks", lambda *a, **k: None)
    monkeypatch.setattr(knowledge_vault_routes.canonical_store, "mark_status", lambda *a, **k: None)

    stale = {  # queued before the rule, or a dead letter replayed now: still carries the workspace entry
        "doc_id": f"{WORKSPACE}:slack:C1:1.2", "tenant_id": WORKSPACE, "user_id": REP, "source": "slack",
        "acl": [f"tenant:{WORKSPACE}", f"user:{REP}", "channel:C1"],
    }
    knowledge_vault_routes.process_embed_job(stale)
    knowledge_vault_routes.process_embed_job(
        {"doc_id": "doc_upload1", "tenant_id": WORKSPACE, "user_id": REP, "source": "USER_UPLOAD", "acl": [f"user:{REP}", f"tenant:{WORKSPACE}"]}
    )

    assert indexed[0].acl == [f"user:{REP}", "channel:C1"]
    assert indexed[1].acl == [f"user:{REP}", f"tenant:{WORKSPACE}"]


def test_a_permission_change_keeps_the_rep_on_the_chunks_but_not_in_the_provider_snapshot():
    store = CanonicalStore(use_db=False)
    chunks = {}
    service = ACLSyncService(store, SimpleNamespace(update_acl_for_doc_id=lambda doc_id, new_acl: chunks.update({doc_id: new_acl})))
    created = _event("gdrive", REP, "file_1", acl=["rep@acme.test"])
    store.record_event(created, status="VECTOR_STORE_INDEXED")

    service.process_acl_change(_event("gdrive", REP, "file_1", acl=["rep@acme.test", "cfo@acme.test"], kind=EventType.ACL_CHANGE))

    [(doc_id, acl)] = chunks.items()
    assert acl == ["rep@acme.test", "cfo@acme.test", f"user:{REP}"]
    # Reconciliation compares the provider's permissions with this snapshot, so the rep's entry isn't in it.
    assert store.get_document(doc_id).acl == ["rep@acme.test", "cfo@acme.test"]


def test_a_sweep_compares_a_listing_only_with_that_reps_documents():
    store = CanonicalStore(use_db=False)
    store.record_event(_event("gdrive", REP, "rep_file"), status="VECTOR_STORE_INDEXED")
    store.record_event(_event("gdrive", TEAMMATE, "teammate_file"), status="VECTOR_STORE_INDEXED")
    sweeper = ReconciliationSweeper(store, DeletionHandler(store), ACLSyncService(store))

    report = sweeper.sweep_source(
        tenant_id=WORKSPACE, source="gdrive", live_source_docs=[{"external_id": "rep_file"}], complete=True, user_id=REP
    )

    assert report.total_checked == 1 and report.missed_deletions_found == 0
    statuses = {doc.external_id: doc.status for doc in store.list_documents(WORKSPACE, "gdrive", exclude_statuses=())}
    assert statuses == {"rep_file": "VECTOR_STORE_INDEXED", "teammate_file": "VECTOR_STORE_INDEXED"}


def _event(source, user, external_id, acl=("x@acme.test",), kind=EventType.CREATE):
    return CanonicalEvent(
        event_id=f"evt_{uuid.uuid4().hex[:8]}", event_type=kind, source=source, tenant_id=WORKSPACE, user_id=user,
        external_id=external_id, raw_ref={}, acl=list(acl), timestamp=datetime.now(timezone.utc),
    )


# --------------------------------------------------------------------------- gatekeeper holds


def test_a_held_synced_document_is_listed_and_released_only_by_its_rep(members, monkeypatch):
    store = GatekeeperStore(use_db=False)
    monkeypatch.setattr(gatekeeper_routes, "gatekeeper_store", store)
    held = f"{WORKSPACE}:gmail:held_1"
    store.hold(KIND_REJECTED, ParsedDocument(
        doc_id=held, tenant_id=WORKSPACE, user_id=REP, source="gmail", external_id="held_1", acl=[REP],
        mime_type="text/plain", text_content="Re: salary review for Q3",
    ), "repetitive noise", ttl_days=30)
    app = FastAPI()
    app.include_router(gatekeeper_routes.router, prefix="/api/v1")
    client = TestClient(app)

    assert client.get("/api/v1/gatekeeper/holds", headers=_as(OWNER)).json()["count"] == 0
    assert client.post(f"/api/v1/gatekeeper/holds/{held}/release", headers=_as(OWNER)).status_code == 404
    assert [h["doc_id"] for h in client.get("/api/v1/gatekeeper/holds", headers=_as(REP)).json()["holds"]] == [held]
    assert client.post(f"/api/v1/gatekeeper/holds/{held}/release", headers=_as(REP)).status_code == 200


# --------------------------------------------------------------------------- webhook attribution


class _Worker:
    def __init__(self):
        self.events = []

    async def _process_event(self, event):
        self.events.append(event)


def _webhook_event(source, user=REP):
    return CanonicalEvent(
        event_id=f"{source}_evt_1", event_type=EventType.CREATE, source=source, tenant_id=WORKSPACE, user_id=user,
        external_id="evt_1", raw_ref={}, acl=[user], metadata={"name": "Notes", "title": "Notes", "text": "Board notes."},
    )


def _teammate_with_webhooks(store):
    theirs = store.get_or_create_connection(tenant_id=WORKSPACE, user_id=TEAMMATE)
    theirs.config.webhook_enabled = True
    store.update_connection(theirs)


@pytest.mark.parametrize(
    "manager_class, store_class, source, build",
    [
        pytest.param(GDriveSyncManager, GDriveStore, "gdrive", lambda cls, store, worker: cls(composio_client=SimpleNamespace(_composio=None), store=store, queue_worker=worker), id="gdrive"),
        pytest.param(CalendarSyncManager, CalendarStore, "google_calendar", lambda cls, store, worker: cls(composio_client=SimpleNamespace(_composio=None), store=store, queue_worker=worker), id="calendar"),
        pytest.param(SlackSyncManager, SlackStore, "slack", lambda cls, store, worker: cls(store=store, composio=SimpleNamespace(), queue_worker=worker), id="slack"),
        pytest.param(NotionSyncManager, NotionStore, "notion", lambda cls, store, worker: cls(store=store, composio=SimpleNamespace(), queue_worker=worker), id="notion"),
    ],
)
def test_an_event_is_never_attributed_to_another_reps_connection(manager_class, store_class, source, build):
    store = store_class()  # in-memory
    _teammate_with_webhooks(store)
    worker = _Worker()
    manager = build(manager_class, store, worker)

    result = asyncio.run(manager.process_webhook_event(_webhook_event(source), raw_payload={}))

    assert result["status"] == "ignored"
    assert worker.events == []
