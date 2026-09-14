"""Connector work that runs outside a request stays inside workspaces too.

Scheduled syncs and reconciliation sweeps skip connections saved before connectors were
workspace-scoped (``tenant_default`` and other non-workspace tenants): nobody can reach,
reconfigure or disconnect those any more, so syncing them would only spend Composio
executions and embedding quota on data no workspace can see. And an event pinned to a
connection is processed there without looking up any other connection.
"""

import asyncio
import sys
import uuid
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from module_1_document_processing.composio_connector.calendar_sync_manager import CalendarSyncManager
from module_1_document_processing.composio_connector.events.canonical_event import CanonicalEvent, EventType
from module_1_document_processing.composio_connector.gdrive_store import GDriveStore
from module_1_document_processing.composio_connector.gdrive_sync_manager import GDriveSyncManager
from module_1_document_processing.composio_connector.gmail_sync_manager import GmailSyncManager
from module_1_document_processing.composio_connector.notion_store import NotionStore
from module_1_document_processing.composio_connector.notion_sync_manager import NotionSyncManager
from module_1_document_processing.composio_connector.slack_store import SlackStore
from module_1_document_processing.composio_connector.slack_sync_manager import SlackSyncManager
from module_1_document_processing.del_acl_and_reconc import reconciliation_scheduler as scheduler_module
from module_1_document_processing.del_acl_and_reconc.reconciliation_scheduler import ReconciliationScheduler
from module_1_document_processing.workspace_access import is_workspace_id

WORKSPACE = str(uuid.uuid4())
OTHER_WORKSPACE = str(uuid.uuid4())
MEMBER, OUTSIDER = str(uuid.uuid4()), str(uuid.uuid4())
LEGACY_TENANTS = ("tenant_default", WORKSPACE.upper(), "acme")


def test_only_a_canonical_workspace_id_counts_as_a_workspace():
    assert is_workspace_id(WORKSPACE)
    for value in ("tenant_default", WORKSPACE.upper(), "{" + WORKSPACE + "}", WORKSPACE.replace("-", ""), "", None):
        assert not is_workspace_id(value)


class _Store:
    def __init__(self, connections):
        self._connections = connections

    def list_all_active_connections(self):
        return list(self._connections)

    def is_locked(self, connection_id):
        return False


def _due_connection(tenant_id):
    """A connected account whose auto-sync is overdue, in every manager's terms."""
    long_ago = datetime.now(timezone.utc) - timedelta(days=2)
    return SimpleNamespace(
        connection_id=f"conn_{tenant_id}_{MEMBER}",
        tenant_id=tenant_id,
        user_id=MEMBER,
        status="Up to Date",
        lock=SimpleNamespace(is_locked=False),
        config=SimpleNamespace(auto_sync_enabled=True, sync_frequency="30m", auto_sync_interval_minutes=30),
        backfill_state=SimpleNamespace(historical_sync_status="COMPLETED"),
        last_successful_sync_at=long_ago,
        created_at=long_ago,
    )


SCHEDULERS = [
    pytest.param(GmailSyncManager, "_auto_sync_cron_loop", "_scheduler_running", "execute_sync_job", id="gmail"),
    pytest.param(GDriveSyncManager, "_auto_sync_loop", "_is_scheduler_running", "start_sync_job", id="gdrive"),
    pytest.param(CalendarSyncManager, "_auto_sync_loop", "_is_scheduler_running", "start_sync_job", id="calendar"),
    pytest.param(SlackSyncManager, "_auto_sync_cron_loop", "_scheduler_running", "execute_sync_job", id="slack"),
    pytest.param(NotionSyncManager, "_auto_sync_cron_loop", "_scheduler_running", "execute_sync_job", id="notion"),
]


@pytest.mark.parametrize("manager_class, loop, running_flag, sync_job", SCHEDULERS)
def test_scheduled_syncs_skip_connections_saved_outside_a_workspace(monkeypatch, manager_class, loop, running_flag, sync_job):
    in_workspace = _due_connection(WORKSPACE)
    manager = manager_class.__new__(manager_class)  # no real store, Composio client or queue
    manager.store = _Store([_due_connection(tenant) for tenant in LEGACY_TENANTS] + [in_workspace])
    manager.composio = SimpleNamespace(is_account_connected=lambda user_id, source: True)
    manager._last_auto_sync_times = {}
    setattr(manager, running_flag, True)

    started = []

    async def record_sync(connection_id, **options):
        started.append(connection_id)

    setattr(manager, sync_job, record_sync)

    sleeps = []

    async def one_pass(seconds):  # each pass starts with a sleep: allow one pass, then stop the loop
        sleeps.append(seconds)
        if len(sleeps) > 1:
            raise asyncio.CancelledError

    monkeypatch.setattr(
        sys.modules[manager_class.__module__],
        "asyncio",
        SimpleNamespace(sleep=one_pass, create_task=asyncio.create_task, CancelledError=asyncio.CancelledError),
    )

    async def run():
        await getattr(manager, loop)()
        started_jobs = [task for task in asyncio.all_tasks() if task is not asyncio.current_task()]
        await asyncio.gather(*started_jobs)

    asyncio.run(run())

    assert started == [in_workspace.connection_id]


def test_scheduled_sweeps_skip_connections_saved_outside_a_workspace(monkeypatch):
    swept = []

    class Lister:
        def __init__(self, composio):
            pass

        def list_source(self, source, user_id):
            return SimpleNamespace(complete=True, items=[{"external_id": "file_1"}], reason="")

    class Sweeper:
        def sweep_source(self, tenant_id, source, live_source_docs, complete, user_id):
            swept.append((tenant_id, source, user_id))
            return SimpleNamespace(tenant_id=tenant_id, source=source)

    monkeypatch.setattr(scheduler_module, "LiveSourceLister", Lister)
    connections = [_due_connection(tenant) for tenant in LEGACY_TENANTS] + [_due_connection(WORKSPACE)]
    scheduler = ReconciliationScheduler(
        providers={"gdrive": SimpleNamespace(store=_Store(connections), composio=None)},
        sweeper=Sweeper(),
    )

    assert len(scheduler.sweep_all()) == 1
    assert swept == [(WORKSPACE, "gdrive", MEMBER)]  # compared with that rep's documents only


class _Worker:
    def __init__(self):
        self.events = []

    async def _process_event(self, event):
        self.events.append(event)


def _refuse_lookups(monkeypatch, store, *lookups):
    def refuse(*args, **kwargs):
        raise AssertionError("an event pinned to a connection must not look up another one")

    for lookup in lookups:
        monkeypatch.setattr(store, lookup, refuse)


def _webhook_connection_elsewhere(store):
    """Another workspace's connection with webhooks on: what the managers would fall back to."""
    other = store.get_or_create_connection(tenant_id=OTHER_WORKSPACE, user_id=OUTSIDER)
    other.config.webhook_enabled = True
    store.update_connection(other)


def _simulated_event(source):
    return CanonicalEvent(
        event_id=f"{source}_{WORKSPACE}_sim_1",
        event_type=EventType.CREATE,
        source=source,
        tenant_id=WORKSPACE,
        user_id=MEMBER,
        external_id="sim_1",
        raw_ref={},
        acl=[MEMBER],
        metadata={"name": "Pricing notes", "title": "Pricing notes", "text": "Globex wants a 12-month term."},
    )


def test_a_pinned_drive_event_is_not_redirected_to_another_connection(monkeypatch):
    store = GDriveStore()  # MongoDB is unreachable in tests, so this is the in-memory store
    _webhook_connection_elsewhere(store)
    mine = store.get_or_create_connection(tenant_id=WORKSPACE, user_id=MEMBER)  # webhooks off
    _refuse_lookups(monkeypatch, store, "get_or_create_connection", "list_all_active_connections")
    worker = _Worker()
    manager = GDriveSyncManager(composio_client=SimpleNamespace(_composio=None), store=store, queue_worker=worker)

    result = asyncio.run(manager.process_webhook_event(_simulated_event("gdrive"), raw_payload={}, connection=mine))

    assert result == {"status": "ignored", "reason": "Webhook triggers are disabled"}
    assert worker.events == []


@pytest.mark.parametrize(
    "manager_class, store_class, source",
    [
        pytest.param(SlackSyncManager, SlackStore, "slack", id="slack"),
        pytest.param(NotionSyncManager, NotionStore, "notion", id="notion"),
    ],
)
def test_a_pinned_event_is_processed_in_the_callers_own_connection(monkeypatch, manager_class, store_class, source):
    store = store_class()  # in-memory
    _webhook_connection_elsewhere(store)
    mine = store.get_or_create_connection(tenant_id=WORKSPACE, user_id=MEMBER)
    _refuse_lookups(
        monkeypatch,
        store,
        "find_connection_by_trigger_id",
        "get_connection",
        "find_active_webhook_connection",
        "list_all_active_connections",
        "get_or_create_connection",
    )
    worker = _Worker()
    manager = manager_class(store=store, composio=SimpleNamespace(), queue_worker=worker)

    result = asyncio.run(manager.process_webhook_event(_simulated_event(source), connection=mine))

    assert result["status"] == "success"
    assert [(event.tenant_id, event.user_id) for event in worker.events] == [(WORKSPACE, MEMBER)]
