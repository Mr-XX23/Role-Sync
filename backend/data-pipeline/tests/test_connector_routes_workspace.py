"""Connector routes act only inside a workspace the caller is a member of.

Connections are keyed by (workspace, verified user). Every connector route runs here with
workspace-service faked and the sync managers replaced by recorders, so what is checked is
who may call each route and which workspace and user reach the managers - not the syncing
itself. Each route is served on an app of its own, so a route shadowed by an earlier
``/connectors/{source}/...`` route is still exercised.
"""

import uuid
from dataclasses import asdict, dataclass
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from module_1_document_processing import workspace_access
from module_1_document_processing.composio_connector import connector_routes
from module_1_document_processing.composio_connector.enterprise_store import EnterpriseStore
from module_1_document_processing.workspace_access import MembershipDirectory, require_workspace_member

WORKSPACE = str(uuid.uuid4())
OTHER_WORKSPACE = str(uuid.uuid4())
MEMBER, VIEWER, OUTSIDER = (str(uuid.uuid4()) for _ in range(3))
ROLES = {
    MEMBER: {WORKSPACE: "MEMBER"},
    VIEWER: {WORKSPACE: "VIEWER"},
    OUTSIDER: {OTHER_WORKSPACE: "OWNER"},
}
SOURCES = ("gmail", "gdrive", "calendar", "slack", "notion")
# Satisfies every request model. The user id in it (and in the query) must be ignored.
BODY = {"user_id": "someone-else", "database_system": "Snowflake", "requirements": "Nightly deals export"}


@dataclass
class FakeConnection:
    connection_id: str
    tenant_id: str
    user_id: str
    status: str = "Available"

    def to_dict(self):
        return asdict(self)


class FakeStore:
    def __init__(self, calls):
        self.calls = calls

    def get_or_create_connection(self, tenant_id, user_id):
        self.calls.append((tenant_id, user_id))
        return FakeConnection(f"conn_{tenant_id}_{user_id}", tenant_id, user_id)

    def is_locked(self, connection_id):
        return False

    def get_activities(self, connection_id, limit=20):
        return []


class FakeManager:
    """Stands in for a sync manager, recording the (workspace, user) of every call."""

    def __init__(self, calls, auto_sync_is_async=False):
        self.calls = calls
        self.store = FakeStore(calls)
        self.pinned = []
        self._auto_sync_is_async = auto_sync_is_async

    def _done(self, tenant_id, user_id):
        self.calls.append((tenant_id, user_id))
        return {"status": "success"}

    def get_connection_status(self, user_id, tenant_id):
        self.calls.append((tenant_id, user_id))
        return FakeConnection("conn", tenant_id, user_id)

    def initiate_oauth_flow(self, user_id, tenant_id, callback_url=None):
        return self._done(tenant_id, user_id)

    def disconnect_connection(self, user_id, tenant_id):
        return self._done(tenant_id, user_id)

    def get_data_summary(self, user_id, tenant_id):
        return self._done(tenant_id, user_id)

    def update_auto_sync_schedule(self, user_id, tenant_id, **schedule):
        result = self._done(tenant_id, user_id)
        if not self._auto_sync_is_async:
            return result

        async def done():  # Gmail's is a coroutine; the other managers answer directly
            return result

        return done()

    async def save_configuration_and_start_sync(self, user_id, tenant_id, **config):
        return self._done(tenant_id, user_id)

    async def trigger_manual_sync(self, user_id, tenant_id):
        return self._done(tenant_id, user_id)

    async def trigger_resync(self, user_id, tenant_id):
        return self._done(tenant_id, user_id)

    async def retry_failed_items(self, user_id, tenant_id):
        return self._done(tenant_id, user_id)

    async def purge_all_connector_data(self, user_id, tenant_id):
        return self._done(tenant_id, user_id)

    async def start_sync_job(self, connection_id, **options):
        pass

    execute_sync_job = start_sync_job

    async def process_webhook_event(self, event, raw_payload=None, connection=None):
        self.pinned.append(connection)
        return self._done(event.tenant_id, event.user_id)


class FakeEnterpriseStore:
    def __init__(self, calls):
        self.calls = calls

    def create_request(self, user_id, tenant_id, **request):
        self.calls.append((tenant_id, user_id))
        return {"request_id": "req_ent_1", "user_id": user_id, "tenant_id": tenant_id}

    def get_requests(self, user_id, tenant_id):
        self.calls.append((tenant_id, user_id))
        return []

    def cancel_request(self, request_id, user_id, tenant_id):
        self.calls.append((tenant_id, user_id))
        return True


def _cases():
    for route in connector_routes.router.routes:
        for method in sorted(route.methods):
            for source in SOURCES if "{source}" in route.path else ("",):
                path = route.path.replace("{source}", source).replace("{request_id}", "req_ent_1")
                yield pytest.param(route, method, path, id=f"{method} {path}")


CASES = list(_cases())
READS = [case for case in CASES if case.values[1] == "GET"]
WRITES = [case for case in CASES if case.values[1] != "GET"]


@pytest.fixture
def calls(monkeypatch):
    calls = []
    monkeypatch.setattr(
        workspace_access,
        "directory",
        MembershipDirectory("http://workspace.test", fetch=lambda base, user, t: ROLES.get(user, {})),
    )
    monkeypatch.setattr(connector_routes, "gmail_sync_manager", FakeManager(calls, auto_sync_is_async=True))
    for name in ("gdrive_sync_manager", "calendar_sync_manager", "slack_sync_manager", "notion_sync_manager"):
        monkeypatch.setattr(connector_routes, name, FakeManager(calls))
    monkeypatch.setattr(
        connector_routes, "connector_service", SimpleNamespace(composio=SimpleNamespace(clear_cache=lambda user_id: None))
    )
    monkeypatch.setattr(connector_routes, "enterprise_store", FakeEnterpriseStore(calls))
    return calls


def send(route, method, path, headers):
    app = FastAPI()
    app.router.routes.append(route)
    return TestClient(app).request(method, f"{path}?user_id=someone-else", headers=headers, json=BODY)


def test_every_connector_route_checks_workspace_membership():
    for route in connector_routes.router.routes:
        assert require_workspace_member in [dependency.call for dependency in route.dependant.dependencies], route.path


@pytest.mark.parametrize("route, method, path", CASES)
def test_nothing_happens_without_a_workspace_the_caller_belongs_to(calls, route, method, path):
    # No workspace means no workspace: there is no shared default to fall back to.
    assert send(route, method, path, {"X-User-Id": MEMBER}).status_code == 400
    assert send(route, method, path, {"X-User-Id": MEMBER, "X-Tenant-Id": "tenant_default"}).status_code == 400
    # A workspace the caller was never in (or was removed from).
    assert send(route, method, path, {"X-User-Id": OUTSIDER, "X-Tenant-Id": WORKSPACE}).status_code == 403
    assert send(route, method, path, {"X-Tenant-Id": WORKSPACE}).status_code == 401
    assert calls == []


@pytest.mark.parametrize("route, method, path", CASES)
def test_members_act_as_themselves_in_the_verified_workspace(calls, route, method, path):
    # Upper-case, so the managers are seen to get the canonical workspace id, not the header.
    response = send(route, method, path, {"X-User-Id": MEMBER, "X-Tenant-Id": WORKSPACE.upper()})

    assert response.status_code == 200, response.text
    assert calls and set(calls) == {(WORKSPACE, MEMBER)}


@pytest.mark.parametrize("route, method, path", READS)
def test_viewers_can_look(calls, route, method, path):
    assert send(route, method, path, {"X-User-Id": VIEWER, "X-Tenant-Id": WORKSPACE}).status_code == 200


@pytest.mark.parametrize("route, method, path", WRITES)
def test_viewers_cannot_change_anything(calls, route, method, path):
    refused = send(route, method, path, {"X-User-Id": VIEWER, "X-Tenant-Id": WORKSPACE})

    assert refused.status_code == 403
    assert refused.json()["detail"] == "Viewers can't make changes in this workspace"
    assert calls == []


@pytest.mark.parametrize("source", ["gdrive", "slack", "notion"])
def test_simulated_webhooks_go_to_the_callers_own_connection(calls, source):
    # These managers otherwise fall back to any webhook-enabled connection, in any workspace.
    app = FastAPI()
    app.include_router(connector_routes.router)

    response = TestClient(app).post(
        f"/connectors/{source}/simulate-webhook", headers={"X-User-Id": MEMBER, "X-Tenant-Id": WORKSPACE}, json={}
    )

    assert response.status_code == 200, response.text
    pinned = getattr(connector_routes, f"{source}_sync_manager").pinned
    assert [(conn.tenant_id, conn.user_id) for conn in pinned] == [(WORKSPACE, MEMBER)]


def test_enterprise_requests_are_listed_and_cancelled_within_the_workspace():
    store = EnterpriseStore()  # MongoDB is unreachable in tests, so this is the in-memory store
    mine = store.create_request(MEMBER, WORKSPACE, "Snowflake", "Nightly deals export")
    store.create_request(MEMBER, OTHER_WORKSPACE, "Postgres", "Accounts table")

    assert [r["request_id"] for r in store.get_requests(MEMBER, WORKSPACE)] == [mine["request_id"]]
    assert store.cancel_request(mine["request_id"], VIEWER, WORKSPACE) is False  # someone else's
    assert store.cancel_request(mine["request_id"], MEMBER, OTHER_WORKSPACE) is False  # another workspace
    assert store.cancel_request(mine["request_id"], MEMBER, WORKSPACE) is True
    assert store.get_requests(MEMBER, WORKSPACE) == []
