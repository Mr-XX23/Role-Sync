"""A workspace that may not spend is refused paid work with 402, before anything is done or stored.

Refused: knowledge-vault upload, URL ingest, reindex, reclassify; catalog findability; every connector
route that starts a sync (config save, sync-now, resync, retry-failed, simulated webhooks); a
reconciliation sweep; releasing a gatekeeper hold (it replays ingestion). Never refused: knowledge search
and catalog search, and connector routes that start nothing.
"""
import uuid
from uuid import UUID

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from billing.preflight import MESSAGES
from catalog.auth import CatalogContext, get_catalog_context
from catalog.routes import get_service
from catalog.routes import router as catalog_router
from catalog.schemas import SemanticSearchResponse
from module_1_document_processing import knowledge_vault_routes as kv
from module_1_document_processing import workspace_access
from module_1_document_processing.composio_connector import connector_routes
from module_1_document_processing.del_acl_and_reconc import reconciliation_routes
from module_1_document_processing.pipeline.durable_queue import DurableQueue
from module_1_document_processing.workspace_access import MembershipDirectory
from module_2_memory_gatekeeper import gatekeeper_routes
from module_2_memory_gatekeeper.gatekeeper_store import GatekeeperStore
from tests.fake_billing import billing  # noqa: F401 - fixture
from tests.fake_redis import FakeRedis
from tests.test_connector_routes_workspace import FakeEnterpriseStore, FakeManager

WORKSPACE = str(uuid.uuid4())
MEMBER, VIEWER = str(uuid.uuid4()), str(uuid.uuid4())
ROLES = {MEMBER: {WORKSPACE: "MEMBER"}, VIEWER: {WORKSPACE: "VIEWER"}}
HEADERS = {"X-User-Id": MEMBER, "X-Tenant-Id": WORKSPACE}
REFUSALS = ["OUT_OF_CREDITS", "CREDITS_SUSPENDED"]


def assert_refused(response, code):
    assert response.status_code == 402, response.text
    assert response.json()["detail"] == {"code": code, "message": MESSAGES[code]}


def test_the_refusal_messages_are_the_contracts():
    assert MESSAGES == {
        "OUT_OF_CREDITS": "Your workspace is out of credits. Buy more credits to keep uploading and syncing.",
        "CREDITS_SUSPENDED": "Credits for this workspace are suspended. Contact support.",
    }


@pytest.fixture(autouse=True)
def members(monkeypatch):
    monkeypatch.setattr(
        workspace_access, "directory", MembershipDirectory("http://workspace.test", fetch=lambda base, user, t: ROLES.get(user, {}))
    )


def forbid(monkeypatch, target, name):
    def refuse(*args, **kwargs):
        raise AssertionError(f"{name} ran although the workspace may not spend")

    monkeypatch.setattr(target, name, refuse)


# =========================================================================
# Knowledge vault
# =========================================================================
@pytest.fixture
def vault(monkeypatch):
    forbid(monkeypatch, kv, "_process_document_background")
    forbid(monkeypatch, kv, "stage_bytes")
    kv._in_memory_docs.clear()
    app = FastAPI()
    app.include_router(kv.router, prefix="/api/v1")
    yield TestClient(app)
    kv._in_memory_docs.clear()


def seed_document(doc_id="doc_seeded01"):
    kv._in_memory_docs[doc_id] = {
        "doc_id": doc_id, "name": "pricing.md", "tenant_id": WORKSPACE, "user_id": MEMBER, "source": "USER_UPLOAD",
        "status": "Indexed", "chunks": 3, "metadata": {"preview_snippet": "Enterprise pricing"},
    }
    return doc_id


@pytest.mark.parametrize("code", REFUSALS)
def test_an_upload_is_refused_before_the_file_is_read_or_stored(vault, billing, code):
    billing.deny(code)

    response = vault.post(
        "/api/v1/knowledge-vault/upload", headers=HEADERS, files={"file": ("pricing.md", b"# Pricing", "text/markdown")}
    )

    assert_refused(response, code)
    assert kv._in_memory_docs == {}
    assert kv.ingest_queue.depth() == 0
    assert billing.checks == [(WORKSPACE, MEMBER)]


@pytest.mark.parametrize("code", REFUSALS)
def test_a_url_ingest_is_refused_before_the_page_is_fetched(vault, billing, monkeypatch, code):
    from module_1_document_processing.pipeline import safe_fetch

    forbid(monkeypatch, safe_fetch, "fetch_public_url")
    billing.deny(code)

    response = vault.post("/api/v1/knowledge-vault/ingest-url", headers=HEADERS, json={"url": "https://example.com/pricing"})

    assert_refused(response, code)
    assert kv._in_memory_docs == {}


@pytest.mark.parametrize("code", REFUSALS)
def test_a_reindex_is_refused_before_the_old_index_is_dropped(vault, billing, monkeypatch, code):
    doc_id = seed_document()
    forbid(monkeypatch, kv, "_drop_index")
    billing.deny(code)

    response = vault.post(f"/api/v1/knowledge-vault/documents/{doc_id}/reindex", headers=HEADERS)

    assert_refused(response, code)
    assert kv._in_memory_docs[doc_id]["status"] == "Indexed"


@pytest.mark.parametrize("code", REFUSALS)
def test_a_reclassify_is_refused_before_the_model_is_called(vault, billing, monkeypatch, code):
    doc_id = seed_document()
    forbid(monkeypatch, kv.sales_classifier, "classify")
    billing.deny(code)

    assert_refused(vault.post(f"/api/v1/knowledge-vault/documents/{doc_id}/reclassify", headers=HEADERS), code)


def test_membership_and_role_are_checked_before_credits(vault, billing):
    billing.deny()

    viewer = vault.post(
        "/api/v1/knowledge-vault/upload",
        headers={"X-User-Id": VIEWER, "X-Tenant-Id": WORKSPACE},
        files={"file": ("pricing.md", b"# Pricing", "text/markdown")},
    )
    outsider = vault.post(
        "/api/v1/knowledge-vault/ingest-url",
        headers={"X-User-Id": str(uuid.uuid4()), "X-Tenant-Id": WORKSPACE},
        json={"url": "https://example.com"},
    )

    assert (viewer.status_code, outsider.status_code) == (403, 403)
    assert billing.checks == []


def test_a_missing_document_is_404_not_402(vault, billing):
    billing.deny()

    assert vault.post("/api/v1/knowledge-vault/documents/doc_missing/reindex", headers=HEADERS).status_code == 404


def test_knowledge_search_is_never_refused_for_credits(vault, billing, monkeypatch):
    billing.deny()
    monkeypatch.setattr(kv.query_embedder, "embed_query", lambda text: [0.1, 0.2])
    monkeypatch.setattr(kv.vector_store, "search_similarity", lambda **kwargs: [])

    response = vault.post("/api/v1/knowledge-vault/search", headers=HEADERS, json={"query": "pricing"})

    assert response.status_code == 200
    assert billing.checks == []


# =========================================================================
# Catalog
# =========================================================================
FINDABILITY = {
    "name": "Studio Headphones Pro", "type": "PRODUCT", "category": "audio",
    "description": "High-fidelity professional closed-back headphones engineered for studio monitoring, mixing, and "
                   "critical listening, with 50mm neodymium drivers, a wide 10Hz to 35kHz frequency response, a detachable "
                   "cable and replaceable memory foam earcups for long sessions.",
}


class _CatalogService:
    def generate_findability(self, **kwargs):
        raise AssertionError("findability ran although the workspace may not spend")

    def semantic_search(self, tenant_id, query, limit=20, expand=True):
        return SemanticSearchResponse(query=query, expanded_terms=[], results=[])


@pytest.fixture
def catalog():
    app = FastAPI()
    app.include_router(catalog_router, prefix="/api/v1/catalog")
    app.dependency_overrides[get_catalog_context] = lambda: CatalogContext(UUID(WORKSPACE), MEMBER, "MEMBER")
    app.dependency_overrides[get_service] = _CatalogService
    return TestClient(app)


@pytest.mark.parametrize("code", REFUSALS)
def test_findability_generation_is_refused_before_the_model_is_called(catalog, billing, code):
    billing.deny(code)

    assert_refused(catalog.post("/api/v1/catalog/ai/generate-findability", headers=HEADERS, json=FINDABILITY), code)
    assert billing.checks == [(UUID(WORKSPACE), MEMBER)]


def test_catalog_search_is_never_refused_for_credits(catalog, billing):
    billing.deny()

    response = catalog.post("/api/v1/catalog/ai/semantic-search", headers=HEADERS, json={"query": "headphones"})

    assert response.status_code == 200
    assert billing.checks == []


# =========================================================================
# Connectors
# =========================================================================
SOURCES = ("gmail", "gdrive", "calendar", "slack", "notion")
PAID_CONNECTOR_ROUTES = (
    [f"/connectors/{s}/config" for s in SOURCES]
    + [f"/connectors/{s}/sync-now" for s in SOURCES]
    + [f"/connectors/{s}/resync" for s in SOURCES]
    + [f"/connectors/{s}/retry-failed" for s in SOURCES]
    + [f"/connectors/{s}/simulate-webhook" for s in ("gmail", "gdrive", "slack", "notion")]
)
FREE_CONNECTOR_ROUTES = [
    ("GET", "/connectors/status"),
    ("GET", "/connectors/gdrive/status"),
    ("POST", "/connectors/gdrive/auto-sync"),
    ("POST", "/connectors/slack/disconnect"),
    ("GET", "/connectors/notion/activities"),
]


@pytest.fixture
def connectors(monkeypatch):
    calls = []
    monkeypatch.setattr(connector_routes, "gmail_sync_manager", FakeManager(calls, auto_sync_is_async=True))
    for name in ("gdrive_sync_manager", "calendar_sync_manager", "slack_sync_manager", "notion_sync_manager"):
        monkeypatch.setattr(connector_routes, name, FakeManager(calls))
    monkeypatch.setattr(connector_routes, "enterprise_store", FakeEnterpriseStore(calls))
    app = FastAPI()
    app.include_router(connector_routes.router)
    return TestClient(app), calls


@pytest.mark.parametrize("path", PAID_CONNECTOR_ROUTES)
def test_connector_routes_that_start_a_sync_are_refused_before_the_manager_runs(connectors, billing, path):
    client, calls = connectors
    billing.deny("CREDITS_SUSPENDED")

    response = client.post(path, headers=HEADERS, json={})

    assert_refused(response, "CREDITS_SUSPENDED")
    assert calls == []


@pytest.mark.parametrize("method, path", FREE_CONNECTOR_ROUTES)
def test_connector_routes_that_start_nothing_are_not_refused(connectors, billing, method, path):
    client, calls = connectors
    billing.deny()

    assert client.request(method, path, headers=HEADERS, json={}).status_code == 200
    assert billing.checks == []


def test_a_member_with_credits_starts_the_sync(connectors, billing):
    client, calls = connectors

    assert client.post("/connectors/gdrive/sync-now", headers=HEADERS).status_code == 200
    assert billing.checks == [(WORKSPACE, MEMBER)]


# =========================================================================
# Reconciliation sweep and gatekeeper release
# =========================================================================
def test_a_manual_reconciliation_sweep_is_refused(billing, monkeypatch):
    forbid(monkeypatch, reconciliation_routes.reconciliation_scheduler, "sweep_all")
    billing.deny()
    app = FastAPI()
    app.include_router(reconciliation_routes.router)

    assert_refused(TestClient(app).post("/reconciliation/sweep", headers=HEADERS, json={}), "OUT_OF_CREDITS")


def test_releasing_a_hold_that_would_replay_ingestion_is_refused_and_the_hold_kept(billing, monkeypatch):
    from tests.test_replay_and_embed_split import OWNER, WORKSPACE as HOLD_WORKSPACE, hold_with_replay

    store = GatekeeperStore(use_db=False)
    queue = DurableQueue(name="t:billing-release", client=FakeRedis(), consumer_id="w1")
    monkeypatch.setattr(gatekeeper_routes, "gatekeeper_store", store)
    monkeypatch.setattr(gatekeeper_routes, "ingest_queue", queue)
    monkeypatch.setattr(
        workspace_access, "directory",
        MembershipDirectory("http://workspace.test", fetch=lambda base, user, t: {HOLD_WORKSPACE: "OWNER"} if user == OWNER else {}),
    )
    hold_with_replay(store)
    billing.deny()
    app = FastAPI()
    app.include_router(gatekeeper_routes.router)

    response = TestClient(app).post(
        "/gatekeeper/holds/doc_held01/release", headers={"X-User-Id": OWNER, "X-Tenant-Id": HOLD_WORKSPACE}
    )

    assert_refused(response, "OUT_OF_CREDITS")
    assert store.get_hold("doc_held01", tenant_id=HOLD_WORKSPACE).status == "HELD"
    assert queue.depth() == 0
