"""Quarantine replay and the split embedding stage.

Two defects this pins down. Releasing a gatekeeper hold changed its status and
nothing else, so the architecture's "replay after human review" loop ended in a
dead end - the person had to find and re-upload the file. And ingestion was one
job, so an embedding failure retried the parser and the classifier too: each
retry paid for LlamaParse and an LLM call that had already succeeded.
"""
import uuid

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from module_1_document_processing import knowledge_vault_routes as kv
from module_1_document_processing import workspace_access
from module_1_document_processing.pipeline.durable_queue import DurableQueue
from module_1_document_processing.pipeline.job_payloads import (
    JOB_CONNECTOR_EVENT,
    JOB_DOCUMENT_EMBED,
    JOB_DOCUMENT_INGEST,
    OUTCOME_EMBED_QUEUED,
    OUTCOME_HELD,
)
from module_1_document_processing.workspace_access import MembershipDirectory
from module_2_memory_gatekeeper import gatekeeper_routes
from module_2_memory_gatekeeper.gatekeeper_store import KIND_REJECTED, GatekeeperStore
from tests.fake_redis import FakeRedis
from tests.test_gatekeeper_policy_and_store import make_doc

WORKSPACE = str(uuid.uuid4())
OWNER, VIEWER = str(uuid.uuid4()), str(uuid.uuid4())
ROLES = {OWNER: {WORKSPACE: "OWNER"}, VIEWER: {WORKSPACE: "VIEWER"}}
CANONICAL = f"{WORKSPACE}:USER_UPLOAD:doc_held01"


# =========================================================================
# Replay: releasing a hold puts the document back on the queue
# =========================================================================
@pytest.fixture
def store(monkeypatch) -> GatekeeperStore:
    store = GatekeeperStore(use_db=False)
    monkeypatch.setattr(gatekeeper_routes, "gatekeeper_store", store)
    return store


@pytest.fixture
def queue(monkeypatch) -> DurableQueue:
    queue = DurableQueue(name="t:replay", client=FakeRedis(), consumer_id="w1")
    monkeypatch.setattr(gatekeeper_routes, "ingest_queue", queue)
    return queue


@pytest.fixture
def client(monkeypatch, store, queue) -> TestClient:
    monkeypatch.setattr(
        workspace_access,
        "directory",
        MembershipDirectory("http://workspace.test", fetch=lambda base, user, t: ROLES.get(user, {})),
    )
    app = FastAPI()
    app.include_router(gatekeeper_routes.router, prefix="/api/v1")
    return TestClient(app)


def release(client, user=OWNER, doc_id="doc_held01"):
    return client.post(
        f"/api/v1/gatekeeper/holds/{doc_id}/release",
        headers={"X-User-Id": user, "X-Tenant-Id": WORKSPACE},
    )


def hold_with_replay(store, payload=None):
    store.hold(KIND_REJECTED, make_doc(doc_id=CANONICAL, tenant_id=WORKSPACE), "low utility", ttl_days=30)
    store.attach_replay(
        "doc_held01",
        {"kind": JOB_DOCUMENT_INGEST, "payload": payload or {
            "doc_id": "doc_held01", "tenant_id": WORKSPACE, "staged_ref": "s3://b/staging/doc_held01",
        }},
        tenant_id=WORKSPACE,
    )


def test_releasing_a_hold_requeues_the_document(client, store, queue):
    hold_with_replay(store)

    response = release(client)

    assert response.status_code == 200
    assert response.json()["requeued"] is True
    job = queue.reserve()
    assert job.kind == JOB_DOCUMENT_INGEST
    assert job.payload["doc_id"] == "doc_held01"
    assert job.payload["staged_ref"] == "s3://b/staging/doc_held01"


def test_the_replayed_job_skips_the_gatekeeper(client, store, queue):
    """Evaluating it again would only reject it again - replay would loop."""
    hold_with_replay(store)

    release(client)

    assert queue.reserve().payload["skip_gatekeeper"] is True


def test_a_release_is_not_repeatable_and_does_not_requeue_twice(client, store, queue):
    hold_with_replay(store)

    assert release(client).status_code == 200
    assert release(client).status_code == 404
    assert queue.depth() == 1


def test_a_hold_from_before_replay_existed_is_released_honestly(client, store, queue):
    """No replay data: say so, rather than claim it was requeued."""
    store.hold(KIND_REJECTED, make_doc(doc_id=CANONICAL, tenant_id=WORKSPACE), "old hold", ttl_days=30)

    body = release(client).json()

    assert body["requeued"] is False
    assert "re-upload" in body["message"].lower()
    assert queue.depth() == 0


def test_a_backlogged_queue_refuses_before_releasing(client, store, queue):
    """Refusing after the release would strand a released-but-never-requeued hold."""
    hold_with_replay(store)
    queue.max_depth = 1
    queue.enqueue("doc", {"doc_id": "someone_else"})

    response = release(client)

    assert response.status_code == 503
    assert response.headers["Retry-After"] == "120"
    assert store.get_hold("doc_held01", tenant_id=WORKSPACE).status == "HELD"  # untouched, retryable


def test_viewers_cannot_replay(client, store, queue):
    hold_with_replay(store)

    assert release(client, user=VIEWER).status_code == 403
    assert queue.depth() == 0


def test_attach_replay_resolves_either_id_form():
    store = GatekeeperStore(use_db=False)
    store.hold(KIND_REJECTED, make_doc(doc_id=CANONICAL, tenant_id=WORKSPACE), "held", ttl_days=30)

    assert store.attach_replay("doc_held01", {"kind": "k", "payload": {}}, tenant_id=WORKSPACE) is True
    assert store.get_hold(CANONICAL, tenant_id=WORKSPACE).replay == {"kind": "k", "payload": {}}
    assert store.attach_replay("doc_missing", {"kind": "k", "payload": {}}, tenant_id=WORKSPACE) is False


def test_attach_replay_is_tenant_scoped():
    store = GatekeeperStore(use_db=False)
    store.hold(KIND_REJECTED, make_doc(doc_id=CANONICAL, tenant_id=WORKSPACE), "held", ttl_days=30)

    assert store.attach_replay("doc_held01", {"kind": "k", "payload": {}}, tenant_id="other-workspace") is False


# ---- the upload stage records replay data and keeps its bytes -------------
@pytest.fixture
def stage_one(monkeypatch):
    """Isolate process_document_job from parsing, storage and the real queue."""
    state = {"discarded": [], "attached": [], "records": {}, "outcome": OUTCOME_EMBED_QUEUED, "kwargs": None}
    monkeypatch.setattr(kv, "load_staged_bytes", lambda ref: b"pdf bytes")
    monkeypatch.setattr(kv, "discard_staged_bytes", lambda ref: state["discarded"].append(ref))
    monkeypatch.setattr(kv, "_find_doc_record", lambda doc_id: state["records"].get(doc_id))
    monkeypatch.setattr(kv, "_save_doc_record", lambda r: state["records"].__setitem__(r["doc_id"], r))

    def background(**kwargs):
        state["kwargs"] = kwargs
        return state["outcome"]

    monkeypatch.setattr(kv, "_process_document_background", background)

    class _Store:
        def attach_replay(self, doc_id, replay, tenant_id=""):
            state["attached"].append((doc_id, replay, tenant_id))
            return True

    monkeypatch.setattr(kv, "gatekeeper_store", _Store())
    return state


UPLOAD = {
    "doc_id": "doc_1", "tenant_id": WORKSPACE, "user_id": OWNER, "filename": "notes.pdf",
    "mime_type": "application/pdf", "source": "USER_UPLOAD", "staged_ref": "s3://b/staging/doc_1",
}


def test_a_held_upload_keeps_its_bytes_and_records_how_to_replay(stage_one):
    stage_one["outcome"] = OUTCOME_HELD

    kv.process_document_job(dict(UPLOAD))

    assert stage_one["discarded"] == []  # the replay needs them
    doc_id, replay, tenant = stage_one["attached"][0]
    assert (doc_id, tenant) == ("doc_1", WORKSPACE)
    assert replay["kind"] == JOB_DOCUMENT_INGEST
    assert replay["payload"]["staged_ref"] == "s3://b/staging/doc_1"


def test_a_re_held_replay_is_evaluated_afresh_next_time(stage_one):
    """The stored replay payload must not carry a stale override flag."""
    stage_one["outcome"] = OUTCOME_HELD

    kv.process_document_job({**UPLOAD, "skip_gatekeeper": True})

    assert "skip_gatekeeper" not in stage_one["attached"][0][1]["payload"]


def test_an_accepted_upload_releases_its_bytes(stage_one):
    kv.process_document_job(dict(UPLOAD))

    assert stage_one["discarded"] == ["s3://b/staging/doc_1"]
    assert stage_one["attached"] == []


def test_the_override_flag_reaches_the_pipeline(stage_one):
    kv.process_document_job({**UPLOAD, "skip_gatekeeper": True})

    assert stage_one["kwargs"]["skip_gatekeeper"] is True


def test_a_replayed_upload_shows_as_in_progress_immediately(stage_one):
    stage_one["records"]["doc_1"] = {"doc_id": "doc_1", "status": "Rejected", "error_message": "held"}

    kv.process_document_job({**UPLOAD, "skip_gatekeeper": True})

    record = stage_one["records"]["doc_1"]
    assert record["status"] == "Parsing"
    assert "error_message" not in record


# =========================================================================
# The embedding stage runs on its own
# =========================================================================
@pytest.fixture
def embed(monkeypatch):
    state = {"records": {}, "text": "Enterprise pricing tiers and renewal terms.", "written": 3,
             "marked": [], "updated_chunks": None, "indexed": 0, "pipeline_doc": None}

    monkeypatch.setattr(kv.raw_document_store, "get_full_text", lambda ref: state["text"])
    monkeypatch.setattr(
        kv.raw_document_store, "update_chunks",
        lambda doc_id, total_chunks, chunk_ids: state.__setitem__("updated_chunks", total_chunks),
    )
    monkeypatch.setattr(kv, "_find_doc_record", lambda doc_id: state["records"].get(doc_id))
    monkeypatch.setattr(kv, "_save_doc_record", lambda r: state["records"].__setitem__(r["doc_id"], r))
    monkeypatch.setattr(kv, "_indexed_chunk_count", lambda doc_id: state["indexed"])
    monkeypatch.setattr(kv.canonical_store, "mark_status", lambda doc_id, status: state["marked"].append((doc_id, status)))

    class _Pipeline:
        def __init__(self, **kwargs):
            pass

        def process_document(self, doc):
            state["pipeline_doc"] = doc
            if isinstance(state["written"], Exception):
                raise state["written"]
            return state["written"]

    monkeypatch.setattr(kv, "BatchIngestionPipeline", _Pipeline)
    monkeypatch.setattr(kv, "EmbeddingWorker", lambda **kwargs: object())
    return state


EMBED = {
    "doc_id": "doc_1", "canonical_doc_id": f"{WORKSPACE}:USER_UPLOAD:doc_1", "text_ref": "doc_1",
    "tenant_id": WORKSPACE, "user_id": OWNER, "source": "USER_UPLOAD", "mime_type": "text/plain",
    "acl": [f"user:{OWNER}"], "parser_used": "local_text", "parse_status": "SUCCESS",
    "metadata": {"category": "PRICING_PACKAGING"}, "embedding_engine": "RoleSync Vector Engine (1536-dim)",
}


def test_embedding_reads_the_persisted_text_not_the_original_file(embed):
    """The point of the split: a retry costs one embeddings call, not a re-parse."""
    embed["records"]["doc_1"] = {"doc_id": "doc_1", "status": "Parsing"}

    kv.process_embed_job(dict(EMBED))

    doc = embed["pipeline_doc"]
    assert doc.text_content == "Enterprise pricing tiers and renewal terms."
    assert doc.doc_id == EMBED["canonical_doc_id"]
    assert doc.metadata["category"] == "PRICING_PACKAGING"


def test_embedding_marks_the_document_indexed_and_completes_lineage(embed):
    embed["records"]["doc_1"] = {"doc_id": "doc_1", "status": "Parsing", "error_message": "stale"}

    kv.process_embed_job(dict(EMBED))

    record = embed["records"]["doc_1"]
    assert record["status"] == "Indexed"
    assert record["chunks"] == 3
    assert "error_message" not in record
    assert embed["marked"] == [(EMBED["canonical_doc_id"], "VECTOR_STORE_INDEXED")]


def test_an_embedding_failure_raises_so_only_this_stage_retries(embed):
    embed["written"] = RuntimeError("gemini-embedding-001 could not embed 3 chunk(s)")

    with pytest.raises(RuntimeError, match="could not embed"):
        kv.process_embed_job(dict(EMBED))


def test_missing_text_fails_loudly(embed):
    embed["text"] = None

    with pytest.raises(RuntimeError, match="Persisted text missing"):
        kv.process_embed_job(dict(EMBED))


def test_unchanged_content_is_not_reported_as_an_error(embed):
    """Zero written can mean every chunk was already indexed - a re-sync of
    unchanged content - which must not become an Error."""
    embed["written"] = 0
    embed["indexed"] = 4
    embed["records"]["doc_1"] = {"doc_id": "doc_1", "status": "Parsing"}

    kv.process_embed_job(dict(EMBED))

    assert embed["records"]["doc_1"]["status"] == "Indexed"
    assert embed["records"]["doc_1"]["chunks"] == 4


def test_genuinely_empty_content_is_an_error(embed):
    embed["written"] = 0
    embed["indexed"] = 0
    embed["records"]["doc_1"] = {"doc_id": "doc_1", "status": "Parsing"}

    kv.process_embed_job(dict(EMBED))

    assert embed["records"]["doc_1"]["status"] == "Error"
    assert embed["records"]["doc_1"]["error_message"] == kv.guards.NO_CONTENT_MESSAGE


def test_connector_documents_keep_their_provider_id(embed):
    """Reconciliation matches on the provider's id, not the canonical one."""
    kv.process_embed_job({**EMBED, "external_id": "gdrive-file-123"})

    assert embed["pipeline_doc"].external_id == "gdrive-file-123"


# ---- the worker can run every job kind it emits --------------------------
def test_a_bare_worker_can_run_embed_jobs():
    """The connector path emits embed jobs. A worker built without main.py's wiring
    used to dead-letter every one of them."""
    from module_1_document_processing.pipeline.queue_worker import QueueWorker

    stub = object()
    worker = QueueWorker(
        scanner=stub, store=stub, parser_service=stub, deletion_handler=stub,
        acl_sync=stub, gatekeeper_engine=stub, ingestion_pipeline=stub,
        queue=DurableQueue(name="t:bare", client=FakeRedis(), consumer_id="w1"),
    )

    assert JOB_DOCUMENT_EMBED in worker._handlers
    assert JOB_CONNECTOR_EVENT in worker._handlers
