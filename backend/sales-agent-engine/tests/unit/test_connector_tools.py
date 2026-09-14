"""Tools for the rep's connected apps, against the in-memory data-pipeline and a Composio double: what the agent
sees, and changes that are refused before approval whenever data-pipeline would do something harmful with them
(a sync of an app that isn't really connected, a settings save that switches auto-sync off)."""

from __future__ import annotations

from typing import Any
from uuid import UUID, uuid4

import pytest
from pydantic import ValidationError

from app.core.context import AgentContext, RunMode
from app.tools.adapters.connectors import connector_tools
from app.tools.registry import ToolDefinition
from app.tools.types import ToolAccessDenied, ToolFailed, ToolInputError, ToolInvocation, UndoInvocation
from tests.fake_data_pipeline import FakeDataPipeline
from tests.support import FakeConnector

CTX = AgentContext(tenant_id=uuid4(), user_id=uuid4(), session_id=uuid4(), mode=RunMode.INTERACTIVE, turn=1)


class Directory:
    def __init__(self, role: str | None = "MEMBER") -> None:
        self.role = role

    async def role_in(self, user_id: UUID, tenant_id: UUID) -> str | None:
        return self.role


def _tools(pipeline: FakeDataPipeline, *, active: set[str] | None = None, role: str = "MEMBER", composio: bool = True) -> dict[str, ToolDefinition]:
    connector = FakeConnector(connected=active if active is not None else {"gmail", "slack"}) if composio else None
    return {tool.name: tool for tool in connector_tools(pipeline.client(), connector, Directory(role))}


async def _read(tool: ToolDefinition, **arguments: Any):
    return await tool.handler(ToolInvocation(CTX, "orchestrator", "r1", tool.input_model.model_validate(arguments)))


async def _run(tool: ToolDefinition, arguments: dict[str, Any], *, call_id: str = "c1"):
    """Like the gate: arguments, access, the approval preview, then the action."""
    args = tool.input_model.model_validate(arguments)
    if tool.acl is not None:
        await tool.acl(CTX, args)
    preview = await tool.build_preview(CTX, args)
    return preview, await tool.handler(ToolInvocation(CTX, "orchestrator", call_id, args))


async def _undo(tool: ToolDefinition, output) -> str:
    assert output.undo is not None and tool.undo_handler is not None
    return await tool.undo_handler(UndoInvocation(CTX, output.undo.args))


def _sent(pipeline: FakeDataPipeline, suffix: str) -> list[Any]:
    return [body for verb, path, body in pipeline.requests if verb == "POST" and path.endswith(suffix)]


async def test_the_agent_sees_each_app_as_the_rep_would():
    pipeline = FakeDataPipeline()
    pipeline.add_connection("gmail", synced=120, auto_sync_enabled=True, sync_frequency="30m", auto_sync_interval_minutes=30)
    pipeline.add_connection("slack", status="Configuration Required")
    pipeline.add_connection("calendar", status="Up to Date", synced=40)  # data-pipeline thinks so; Composio has no account
    tools = _tools(pipeline)

    output = await _read(tools["list_connected_apps"])

    states = {app["app"]: app["state"] for app in output.data["apps"]}
    assert states == {"gmail": "connected", "calendar": "not connected", "slack": "needs setup", "drive": "not connected", "notion": "not connected"}
    [gmail] = [app for app in output.data["apps"] if app["app"] == "gmail"]
    assert gmail["auto_sync"] == "every 30 minutes" and gmail["items_synced"] == 120
    assert gmail["syncs"] == {"up_to": 10, "unit": "emails", "days_back": 180, "what": ["INBOX"]}
    assert output.data["connect_on"] == "/salesman/external-connector"
    assert output.summary.startswith("Gmail: connected, auto-sync every 30 minutes, 120 synced; Google Calendar: not connected")

    # Without a Composio client, data-pipeline's own status decides.
    no_composio = await _read(_tools(pipeline, composio=False)["list_connected_apps"])
    assert {app["app"]: app["state"] for app in no_composio.data["apps"]}["calendar"] == "connected"


async def test_a_sync_is_refused_before_approval_unless_the_app_is_connected_set_up_and_idle():
    pipeline = FakeDataPipeline()
    pipeline.add_connection("calendar", status="Up to Date")  # no Composio account behind it
    pipeline.add_connection("slack", status="Configuration Required")
    pipeline.add_connection("gmail", locked=True)
    tools = _tools(pipeline)
    sync = tools["sync_app_now"]

    for app, refusal in (
        ("calendar", "isn't connected: the rep connects it on the Connectors page"),
        ("slack", "connected but not set up in this workspace"),
        ("gmail", "already running"),
        ("notion", "isn't connected"),
    ):
        with pytest.raises(ToolInputError, match=refusal):
            await sync.build_preview(CTX, sync.input_model.model_validate({"app": app}))
    assert pipeline.syncs_started == []

    pipeline.add_connection("gmail", locked=False, synced=12)
    preview, output = await _run(sync, {"app": "gmail"})

    assert preview == {"kind": "connector_sync", "app": "gmail", "name": "Gmail", "up_to": 10, "unit": "emails", "items_synced": 12}
    assert pipeline.syncs_started == ["gmail"]
    assert output.summary.startswith("Started a Gmail sync (up to 10 new emails)") and output.undo is None


async def test_a_sync_that_another_started_meanwhile_is_reported_as_running():
    pipeline = FakeDataPipeline()
    pipeline.add_connection("gmail")
    pipeline.failures[("POST", "/api/v1/connectors/gmail/sync-now")] = 409
    tools = _tools(pipeline)

    with pytest.raises(ToolFailed, match="already running"):
        await _run(tools["sync_app_now"], {"app": "gmail"})


async def test_a_settings_change_keeps_everything_else_including_auto_sync_and_can_be_undone():
    pipeline = FakeDataPipeline()
    pipeline.add_connection("gmail", auto_sync_enabled=True, sync_frequency="1h", auto_sync_interval_minutes=60, webhook_enabled=True)
    tools = _tools(pipeline)
    settings = tools["change_app_sync_settings"]

    preview, output = await _run(settings, {"app": "gmail", "max_per_sync": 20, "categories": ["sent"]})

    assert preview["kind"] == "connector_settings" and preview["changes"] == [
        {"field": "max_per_sync", "before": 10, "after": 20},
        {"field": "categories", "before": ["INBOX"], "after": ["SENT"]},
    ]
    [saved] = _sent(pipeline, "/gmail/config")
    assert saved == {
        "max_emails_per_sync": 20, "categories": ["SENT"], "sync_window_days": 180, "auto_sync_interval_minutes": 60,
        "sync_frequency": "1h", "auto_sync_enabled": True, "webhook_enabled": True,
    }
    config = pipeline.connections["gmail"]["config"]
    assert (config["auto_sync_enabled"], config["sync_frequency"]) == (True, "1h")  # still on: the whole config was sent
    assert output.summary == "Gmail sync settings changed: per sync 10 → 20; syncs inbox → sent. A sync has started."

    assert await _undo(settings, output) == "put back 2 settings of Gmail (a sync has started)"
    assert (config := pipeline.connections["gmail"]["config"])["max_emails_per_sync"] == 10 and config["categories"] == ["INBOX"]
    assert config["auto_sync_enabled"] is True
    assert await _undo(settings, output) == "Gmail already syncs the way it did before"

    with pytest.raises(ToolInputError, match="nothing to change"):
        await _run(settings, {"app": "gmail", "window_days": 180})


def test_settings_are_checked_for_each_app_before_anything_runs():
    args = _tools(FakeDataPipeline())["change_app_sync_settings"].input_model
    for wrong in (
        {"app": "gmail", "categories": ["INBOX", "SENT"]},  # Gmail would need both labels on every email
        {"app": "gmail", "categories": ["SPAM"]},
        {"app": "drive", "categories": ["SHARED"]},  # data-pipeline doesn't filter Drive
        {"app": "gmail", "max_per_sync": 31},
        {"app": "slack", "future_window_days": 30},
        {"app": "notion"},
    ):
        with pytest.raises(ValidationError):
            args.model_validate(wrong)
    assert args.model_validate({"app": "calendar", "max_per_sync": 50, "future_window_days": 90}).max_per_sync == 50
    assert args.model_validate({"app": "slack", "categories": ["direct_messages", "DIRECT_MESSAGES"]}).categories == ["DIRECT_MESSAGES"]


async def test_the_schedule_is_set_without_touching_webhooks_and_undo_puts_it_back():
    pipeline = FakeDataPipeline()
    pipeline.add_connection("slack", webhook_enabled=True)
    tools = _tools(pipeline)
    schedule = tools["set_app_auto_sync"]

    preview, output = await _run(schedule, {"app": "slack", "schedule": "every 6 hours"})

    assert preview == {"kind": "connector_schedule", "app": "slack", "name": "Slack", "before": "off", "after": "every 6 hours"}
    assert _sent(pipeline, "/slack/auto-sync") == [{"sync_frequency": "6h", "interval_minutes": 360, "auto_sync_enabled": True, "webhook_enabled": True}]
    assert output.summary == "Slack auto-sync: off → every 6 hours"
    assert await _undo(schedule, output) == "Slack auto-sync is off again"
    assert pipeline.connections["slack"]["config"]["auto_sync_enabled"] is False

    with pytest.raises(ToolInputError, match="Notion isn't connected"):
        await _run(schedule, {"app": "notion", "schedule": "every hour"})
    pipeline.add_connection("notion", status="Available", auto_sync_enabled=True, sync_frequency="30m", auto_sync_interval_minutes=30)
    _, turned_off = await _run(schedule, {"app": "notion", "schedule": "off"})  # turning it off is always fine
    assert turned_off.summary == "Notion auto-sync: every 30 minutes → off"


async def test_disconnecting_says_what_it_stops_and_cannot_be_undone():
    pipeline = FakeDataPipeline()
    pipeline.add_connection("gmail", synced=300)
    tools = _tools(pipeline)
    disconnect = tools["disconnect_app"]
    assert disconnect.irreversible and disconnect.undo_handler is None

    preview, output = await _run(disconnect, {"app": "gmail"})

    assert preview == {"kind": "connector_disconnect", "app": "gmail", "name": "Gmail", "items_synced": 300, "unit": "emails"}
    assert pipeline.connections["gmail"]["status"] == "Disconnected"
    assert "stays in the rep's knowledge base" in output.summary

    with pytest.raises(ToolInputError, match="Notion isn't connected"):
        await _run(disconnect, {"app": "notion"})


async def test_viewers_are_refused_before_approval():
    pipeline = FakeDataPipeline()
    pipeline.add_connection("gmail")
    tools = _tools(pipeline, role="VIEWER")

    for name, arguments in (("sync_app_now", {"app": "gmail"}), ("disconnect_app", {"app": "gmail"}),
                            ("set_app_auto_sync", {"app": "gmail", "schedule": "every day"})):
        with pytest.raises(ToolAccessDenied, match="viewers"):
            await _run(tools[name], arguments)
    assert pipeline.syncs_started == [] and pipeline.connections["gmail"]["status"] == "Up to Date"


async def test_sync_history_says_what_happened_and_what_failed():
    pipeline = FakeDataPipeline()
    pipeline.connector_history["gmail"] = [
        {"trigger_type": "MANUAL_SYNC", "status": "PARTIAL_SUCCESS", "started_at": "2026-09-15T09:00:00+00:00",
         "completed_at": "2026-09-15T09:01:00+00:00", "metrics": {"total_discovered": 12, "succeeded": 10, "skipped": 1, "failed": 1},
         "items": [{"subject": "Re: renewal", "status": "SUCCESS"}, {"subject": "Invoice.pdf", "status": "FAILED", "error_message": "attachment too large"}]},
        {"trigger_type": "AUTO_SYNC", "status": "COMPLETED", "started_at": "2026-09-15T08:00:00+00:00", "metrics": {"succeeded": 3}, "items": []},
    ]
    tools = _tools(pipeline)

    output = await _read(tools["get_app_sync_history"], app="gmail", max_results=5)

    first, second = output.data["syncs"]
    assert (first["trigger"], first["status"], first["added"], first["failed"]) == ("manual", "partial success", 10, 1)
    assert first["failed_items"] == [{"item": "Invoice.pdf", "error": "attachment too large"}]
    assert (second["trigger"], second["status"]) == ("scheduled", "completed")
    assert output.summary == "Last Gmail sync (manual, 2026-09-15T09:00:00+00:00): partial success, 10 emails added, 1 failed"

    empty = await _read(tools["get_app_sync_history"], app="notion")
    assert empty.summary == "Notion hasn't synced in this workspace yet"
