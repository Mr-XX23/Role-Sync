"""The rep's connected apps (Gmail, Google Calendar, Slack, Google Drive, Notion), over data-pipeline's connectors.

What an app syncs goes into the rep's private part of the knowledge base (only they and their agent can search
it). The agent can see how each app is connected and syncing, start a sync, change what is synced and how often,
and disconnect an app; each change pauses for the rep's approval. Connecting an app needs the rep in a browser, so
the agent sends them to the Connectors page instead.

data-pipeline's connector API has sharp edges these tools stay clear of:
- A sync for an app that isn't really connected ends as if everything had been synced, so the app's history is
  skipped once it is connected. Every write checks the rep's actual connection (Composio lists it ACTIVE) first
  and refuses before anyone is asked.
- Saving an app's settings replaces the whole configuration, and fields not sent fall back to defaults (auto-sync
  off). So a settings change sends the current configuration with only the changed fields replaced.
- Saving settings starts a sync, and so does an undo of one.
- Disconnecting removes the rep's account for that app everywhere: every workspace, and the agent's own email,
  calendar, Slack or Notion tools, until they connect it again in a browser. It can't be undone here.
- Resync, retrying failed items (a full resync underneath) and webhooks stay in the app, and the agent offers
  auto-sync every 30 minutes at most (a Slack sync can use a hundred Composio actions).
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any, Literal
from uuid import UUID

from pydantic import Field, model_validator

from app.core.context import AgentContext
from app.platform.composio_client import ConnectorClient, ConnectorError
from app.platform.data_pipeline import DataPipelineClient, DataPipelineError
from app.platform.workspace_client import WorkspaceDirectory
from app.tools.adapters.common import clip, pipeline_failure, pipeline_write_failure, plural
from app.tools.registry import AclCheck, ToolDefinition
from app.tools.types import (
    SourceLink,
    ToolAccessDenied,
    ToolCategory,
    ToolFailed,
    ToolInput,
    ToolInputError,
    ToolInvocation,
    ToolKind,
    ToolOutput,
    ToolScope,
    UndoInvocation,
    UndoPlan,
)

CONNECTORS_PAGE = "/salesman/external-connector"

AppKey = Literal["gmail", "calendar", "slack", "drive", "notion"]
Schedule = Literal["off", "every 30 minutes", "every hour", "every 6 hours", "every day"]


@dataclass(frozen=True, slots=True)
class App:
    name: str  # what the rep calls it
    source: str  # data-pipeline's name: its routes and status key
    toolkit: str  # Composio toolkit
    unit: str  # what one synced item is
    max_field: str  # the configuration field limiting each sync
    max_per_sync: int
    # What the rep can choose to sync. Empty: data-pipeline ignores choices for this app (Drive reads every file,
    # Calendar the primary calendar), so there is nothing to offer.
    categories: tuple[str, ...] = ()
    one_category: bool = False  # Gmail matches mail carrying ALL the chosen labels, so one label at a time


APPS: dict[str, App] = {
    "gmail": App("Gmail", "gmail", "gmail", "emails", "max_emails_per_sync", 30, ("INBOX", "SENT", "IMPORTANT", "STARRED", "ALL"), True),
    "calendar": App("Google Calendar", "calendar", "googlecalendar", "events", "max_events_per_sync", 50),
    "slack": App("Slack", "slack", "slack", "messages", "max_messages_per_sync", 30, ("PUBLIC_CHANNELS", "PRIVATE_CHANNELS", "DIRECT_MESSAGES", "GROUP_MESSAGES")),
    "drive": App("Google Drive", "gdrive", "googledrive", "files", "max_files_per_sync", 30),
    "notion": App("Notion", "notion", "notion", "pages", "max_records_per_sync", 30, ("PAGES", "DATABASES")),
}
# (data-pipeline frequency, minutes) for each schedule the agent may set
SCHEDULES: dict[str, tuple[str, int]] = {
    "off": ("off", 0),
    "every 30 minutes": ("30m", 30),
    "every hour": ("1h", 60),
    "every 6 hours": ("6h", 360),
    "every day": ("24h", 1440),
}
_TRIGGERS = {"INITIAL_SYNC": "first sync", "AUTO_SYNC": "scheduled", "MANUAL_SYNC": "manual", "RESYNC": "resync", "WEBHOOK": "webhook"}


class ListConnectedAppsArgs(ToolInput):
    pass


class AppArgs(ToolInput):
    app: AppKey


class SyncHistoryArgs(ToolInput):
    app: AppKey
    max_results: int = Field(default=5, ge=1, le=20)


class SyncSettingsArgs(ToolInput):
    """Only what is passed changes."""

    app: AppKey
    max_per_sync: int | None = Field(default=None, ge=1, le=50, description="How many new items one sync takes in")
    window_days: int | None = Field(default=None, ge=1, le=365, description="How far back the first syncs reach, in days")
    categories: list[str] | None = Field(
        default=None, max_length=4,
        description="Gmail: one of INBOX, SENT, IMPORTANT, STARRED, ALL. Slack: PUBLIC_CHANNELS, PRIVATE_CHANNELS, "
        "DIRECT_MESSAGES, GROUP_MESSAGES. Notion: PAGES, DATABASES. Not for Calendar or Drive.",
    )
    future_window_days: int | None = Field(default=None, ge=1, le=730, description="Calendar only: how far ahead, in days")

    @model_validator(mode="after")
    def _fits_the_app(self) -> SyncSettingsArgs:
        app = APPS[self.app]
        if self.max_per_sync is not None and self.max_per_sync > app.max_per_sync:
            raise ValueError(f"{app.name} takes in at most {app.max_per_sync} {app.unit} per sync")
        if self.categories is not None:
            if not app.categories:
                raise ValueError(f"{app.name} doesn't let you choose what to sync")
            chosen = [category.strip().upper() for category in self.categories if category.strip()]
            unknown = sorted(set(chosen) - set(app.categories))
            if unknown or not chosen:
                raise ValueError(f"{app.name} categories are {', '.join(app.categories)}")
            if app.one_category and len(chosen) != 1:
                raise ValueError("Gmail syncs one label at a time (mail must carry every label chosen)")
            self.categories = list(dict.fromkeys(chosen))
        if self.future_window_days is not None and self.app != "calendar":
            raise ValueError("future_window_days is for Google Calendar only")
        if all(value is None for value in (self.max_per_sync, self.window_days, self.categories, self.future_window_days)):
            raise ValueError("pass at least one setting to change")
        return self


class AutoSyncArgs(ToolInput):
    app: AppKey
    schedule: Schedule


def connector_tools(
    pipeline: DataPipelineClient, connector: ConnectorClient | None, directory: WorkspaceDirectory
) -> list[ToolDefinition]:
    writer = _writer_required(directory)

    async def connected(user_id: UUID, app: App) -> bool | None:
        """Whether the rep's account for the app is ACTIVE (None: can't tell; data-pipeline's status decides)."""
        if connector is None:
            return None
        try:
            return await connector.has_active_connection(user_id, app.toolkit)
        except ConnectorError:
            return None

    async def statuses(ctx: AgentContext) -> dict[str, dict[str, Any]]:
        try:
            return await pipeline.connector_status(ctx.user_id, ctx.tenant_id)
        except DataPipelineError as exc:
            raise pipeline_failure(exc) from exc

    async def current(ctx: AgentContext, app: App) -> tuple[dict[str, Any], str]:
        found, is_connected = await asyncio.gather(statuses(ctx), connected(ctx.user_id, app))
        status = found.get(app.source) or {}
        return status, _state(status, is_connected)

    # ------------------------------------------------------------------ reads
    async def list_connected_apps(invocation: ToolInvocation) -> ToolOutput:
        ctx = invocation.ctx
        found = await statuses(ctx)
        checks = await asyncio.gather(*(connected(ctx.user_id, app) for app in APPS.values()))
        apps = [_view(key, app, found.get(app.source) or {}, is_connected) for (key, app), is_connected in zip(APPS.items(), checks)]
        return ToolOutput(
            data={"apps": apps, "connect_on": CONNECTORS_PAGE},
            summary="; ".join(_brief(entry) for entry in apps),
            sources=(SourceLink(title="Connectors", url=CONNECTORS_PAGE),),
        )

    async def get_app_sync_history(invocation: ToolInvocation) -> ToolOutput:
        args = invocation.args
        assert isinstance(args, SyncHistoryArgs)
        ctx = invocation.ctx
        app = APPS[args.app]
        try:
            activities = await pipeline.connector_activities(ctx.user_id, ctx.tenant_id, app.source, limit=args.max_results)
        except DataPipelineError as exc:
            raise pipeline_failure(exc) from exc
        syncs = [_sync_view(activity) for activity in activities[: args.max_results]]
        if not syncs:
            summary = f"{app.name} hasn't synced in this workspace yet"
        else:
            last = syncs[0]
            summary = f"Last {app.name} sync ({last['trigger']}, {last['started_at']}): {last['status']}, {plural(last['added'], app.unit[:-1] if app.unit.endswith('s') else app.unit)} added"
            if last["failed"]:
                summary += f", {last['failed']} failed"
        return ToolOutput(data={"app": args.app, "syncs": syncs}, summary=summary, sources=(SourceLink(title="Connectors", url=CONNECTORS_PAGE),))

    # ------------------------------------------------------------------ sync now
    async def sync_preview(ctx: AgentContext, args: ToolInput) -> dict[str, Any]:
        assert isinstance(args, AppArgs)
        app = APPS[args.app]
        status, state = await current(ctx, app)
        _require_syncable(app, state)
        config = status.get("config") or {}
        return {
            "kind": "connector_sync",
            "app": args.app,
            "name": app.name,
            "up_to": config.get(app.max_field),
            "unit": app.unit,
            "items_synced": _synced(status),
        }

    async def sync_app_now(invocation: ToolInvocation) -> ToolOutput:
        args = invocation.args
        assert isinstance(args, AppArgs)
        ctx = invocation.ctx
        app = APPS[args.app]
        status, state = await current(ctx, app)
        _require_syncable(app, state)
        try:
            await pipeline.start_connector_sync(ctx.user_id, ctx.tenant_id, app.source)
        except DataPipelineError as exc:
            if exc.status == 409:
                raise ToolFailed(f"a {app.name} sync is already running; check get_app_sync_history in a minute") from exc
            raise pipeline_write_failure(exc) from exc
        up_to = (status.get("config") or {}).get(app.max_field)
        return ToolOutput(
            data={"app": args.app, "started": True},
            summary=f"Started a {app.name} sync" + (f" (up to {up_to} new {app.unit})" if up_to else "") + ". It runs in the background: check get_app_sync_history in a minute.",
            sources=(SourceLink(title="Connectors", url=CONNECTORS_PAGE),),
        )

    # ------------------------------------------------------------------ settings
    async def settings_preview(ctx: AgentContext, args: ToolInput) -> dict[str, Any]:
        assert isinstance(args, SyncSettingsArgs)
        app = APPS[args.app]
        status, state = await current(ctx, app)
        _require_configurable(app, state)
        changes, _ = plan_settings(app, args, status.get("config") or {})
        if not changes:
            raise ToolInputError(f"nothing to change: {app.name} already syncs this way")
        return {"kind": "connector_settings", "app": args.app, "name": app.name, "changes": changes, "unit": app.unit}

    async def change_app_sync_settings(invocation: ToolInvocation) -> ToolOutput:
        args = invocation.args
        assert isinstance(args, SyncSettingsArgs)
        ctx = invocation.ctx
        app = APPS[args.app]
        status, state = await current(ctx, app)
        _require_configurable(app, state)
        config = dict(status.get("config") or {})
        changes, body = plan_settings(app, args, config)
        if not changes:
            raise ToolInputError(f"nothing to change: {app.name} already syncs this way")
        await save_config(ctx, app, body)
        return ToolOutput(
            data={"app": args.app, "changes": changes},
            summary=f"{app.name} sync settings changed: " + "; ".join(_describe(change) for change in changes) + ". A sync has started.",
            sources=(SourceLink(title="Connectors", url=CONNECTORS_PAGE),),
            undo=UndoPlan(
                args={
                    "app": args.app,
                    "restore": {change["field"]: change["before"] for change in changes},
                    "applied": {change["field"]: change["after"] for change in changes},
                },
                label=f"Put back the previous {app.name} sync settings (starts a sync)",
            ),
        )

    async def save_config(ctx: AgentContext, app: App, body: dict[str, Any]) -> None:
        try:
            answer = await pipeline.save_connector_config(ctx.user_id, ctx.tenant_id, app.source, body)
        except DataPipelineError as exc:
            raise pipeline_write_failure(exc) from exc
        if isinstance(answer, dict) and answer.get("status") == "error":  # Slack and Notion refuse with a 200
            raise ToolFailed(str(answer.get("message") or f"{app.name} didn't accept the settings"))

    async def restore_settings(invocation: UndoInvocation) -> str:
        ctx = invocation.ctx
        app = APPS[str(invocation.args.get("app"))]
        restore = dict(invocation.args.get("restore") or {})
        applied = dict(invocation.args.get("applied") or {})
        status, state = await current(ctx, app)
        if state == "not connected":
            raise ToolFailed(f"{app.name} isn't connected any more, so its settings can't be changed")
        config = dict(status.get("config") or {})
        waiting = {field: value for field, value in restore.items() if _setting(config, app, field) != value}
        if not waiting:
            return f"{app.name} already syncs the way it did before"
        restorable = {field: value for field, value in waiting.items() if _setting(config, app, field) == applied.get(field)}
        if not restorable:
            return f"nothing was put back: the {app.name} settings changed again since"
        body = _full_config(app, config) | {_config_field(app, field): value for field, value in restorable.items()}
        await save_config(ctx, app, body)
        return f"put back {plural(len(restorable), 'setting')} of {app.name} (a sync has started)"

    # ------------------------------------------------------------------ schedule
    async def schedule_preview(ctx: AgentContext, args: ToolInput) -> dict[str, Any]:
        assert isinstance(args, AutoSyncArgs)
        app = APPS[args.app]
        status, state = await current(ctx, app)
        before = _schedule(status.get("config") or {})
        _require_schedulable(app, state, args.schedule)
        if before == args.schedule:
            raise ToolInputError(f"nothing to change: {app.name} auto-sync is already {args.schedule}")
        return {"kind": "connector_schedule", "app": args.app, "name": app.name, "before": before, "after": args.schedule}

    async def set_app_auto_sync(invocation: ToolInvocation) -> ToolOutput:
        args = invocation.args
        assert isinstance(args, AutoSyncArgs)
        ctx = invocation.ctx
        app = APPS[args.app]
        status, state = await current(ctx, app)
        config = status.get("config") or {}
        before = _schedule(config)
        _require_schedulable(app, state, args.schedule)
        if before == args.schedule:
            raise ToolInputError(f"nothing to change: {app.name} auto-sync is already {args.schedule}")
        await apply_schedule(ctx, app, args.schedule, config)
        return ToolOutput(
            data={"app": args.app, "before": before, "after": args.schedule},
            summary=f"{app.name} auto-sync: {before} → {args.schedule}",
            sources=(SourceLink(title="Connectors", url=CONNECTORS_PAGE),),
            undo=UndoPlan(
                args={"app": args.app, "restore": before, "applied": args.schedule},
                label=f"Put back {app.name} auto-sync {before}",
            ),
        )

    async def apply_schedule(ctx: AgentContext, app: App, schedule: str, config: dict[str, Any]) -> None:
        enabled = True
        if schedule in SCHEDULES:
            frequency, minutes = SCHEDULES[schedule]
            enabled = minutes > 0
        elif schedule == "on changes only":  # an undo back to webhook-only syncing, set in the app
            frequency, minutes = "realtime", 0
        else:  # an undo back to an interval set in the app that the agent doesn't offer
            minutes = _minutes(schedule)
            frequency = f"{minutes}m"
        body = {
            "sync_frequency": frequency,
            "interval_minutes": minutes,
            "auto_sync_enabled": enabled,
            "webhook_enabled": bool(config.get("webhook_enabled")),  # left as it is
        }
        try:
            answer = await pipeline.set_connector_schedule(ctx.user_id, ctx.tenant_id, app.source, body)
        except DataPipelineError as exc:
            raise pipeline_write_failure(exc) from exc
        if isinstance(answer, dict) and answer.get("status") == "error":
            raise ToolFailed(str(answer.get("message") or f"{app.name} didn't accept the schedule"))

    async def restore_schedule(invocation: UndoInvocation) -> str:
        ctx = invocation.ctx
        app = APPS[str(invocation.args.get("app"))]
        restore, applied = str(invocation.args.get("restore")), str(invocation.args.get("applied"))
        status, _ = await current(ctx, app)
        config = status.get("config") or {}
        now = _schedule(config)
        if now == restore:
            return f"{app.name} auto-sync is already {restore}"
        if now != applied:
            return f"nothing was put back: {app.name} auto-sync changed again since (now {now})"
        await apply_schedule(ctx, app, restore, config)
        return f"{app.name} auto-sync is {restore} again"

    # ------------------------------------------------------------------ disconnect
    async def disconnect_preview(ctx: AgentContext, args: ToolInput) -> dict[str, Any]:
        assert isinstance(args, AppArgs)
        app = APPS[args.app]
        status, state = await current(ctx, app)
        if state == "not connected":
            raise ToolInputError(f"{app.name} isn't connected")
        return {"kind": "connector_disconnect", "app": args.app, "name": app.name, "items_synced": _synced(status), "unit": app.unit}

    async def disconnect_app(invocation: ToolInvocation) -> ToolOutput:
        args = invocation.args
        assert isinstance(args, AppArgs)
        ctx = invocation.ctx
        app = APPS[args.app]
        _, state = await current(ctx, app)
        if state == "not connected":
            raise ToolInputError(f"{app.name} isn't connected")
        try:
            await pipeline.disconnect_connector(ctx.user_id, ctx.tenant_id, app.source)
        except DataPipelineError as exc:
            raise pipeline_write_failure(exc) from exc
        return ToolOutput(
            data={"app": args.app, "disconnected": True},
            summary=(
                f"Disconnected {app.name}. What it synced stays in the rep's knowledge base; to use it again they "
                "connect it on the Connectors page."
            ),
            sources=(SourceLink(title="Connectors", url=CONNECTORS_PAGE),),
        )

    return [
        ToolDefinition(
            name="list_connected_apps",
            description=(
                "The rep's apps (Gmail, Google Calendar, Slack, Google Drive, Notion): whether each is connected in "
                "this workspace, how often it syncs, what it syncs and how much it has synced, and where to connect one."
            ),
            kind=ToolKind.READ,
            scope=ToolScope.READ,
            category=ToolCategory.KNOWLEDGE,
            input_model=ListConnectedAppsArgs,
            handler=list_connected_apps,
            timeout_seconds=30,
        ),
        ToolDefinition(
            name="get_app_sync_history",
            description="Recent syncs of one of the rep's apps, newest first: when, why, what was added and what failed.",
            kind=ToolKind.READ,
            scope=ToolScope.READ,
            category=ToolCategory.KNOWLEDGE,
            input_model=SyncHistoryArgs,
            handler=get_app_sync_history,
            timeout_seconds=20,
        ),
        ToolDefinition(
            name="sync_app_now",
            description=(
                "Start a sync of one of the rep's connected apps now; it runs in the background and adds what is new "
                "to their private knowledge base. The rep approves it."
            ),
            kind=ToolKind.WRITE,
            scope=ToolScope.CONNECTORS,
            category=ToolCategory.ACTION,
            input_model=AppArgs,
            handler=sync_app_now,
            timeout_seconds=30,
            acl=writer,
            preview=sync_preview,
        ),
        ToolDefinition(
            name="change_app_sync_settings",
            description=(
                "Change what one of the rep's apps syncs: how many new items per sync, how many days back, and for "
                "Gmail, Slack and Notion which kinds of items. Only the settings you pass change. Saving starts a "
                "sync. The rep approves it."
            ),
            kind=ToolKind.WRITE,
            scope=ToolScope.CONNECTORS,
            category=ToolCategory.ACTION,
            input_model=SyncSettingsArgs,
            handler=change_app_sync_settings,
            timeout_seconds=30,
            acl=writer,
            preview=settings_preview,
            undo_handler=restore_settings,
        ),
        ToolDefinition(
            name="set_app_auto_sync",
            description=(
                "Turn automatic syncing of one of the rep's apps off, or on every 30 minutes, hour, 6 hours or day. "
                "The rep approves it."
            ),
            kind=ToolKind.WRITE,
            scope=ToolScope.CONNECTORS,
            category=ToolCategory.ACTION,
            input_model=AutoSyncArgs,
            handler=set_app_auto_sync,
            timeout_seconds=30,
            acl=writer,
            preview=schedule_preview,
            undo_handler=restore_schedule,
        ),
        ToolDefinition(
            name="disconnect_app",
            description=(
                "Disconnect one of the rep's apps. This signs RoleSync out of it in every workspace and stops your own "
                "tools for that app until the rep connects it again in a browser; what it synced stays. Tell the rep "
                "this before proposing it. The rep approves it."
            ),
            kind=ToolKind.WRITE,
            scope=ToolScope.CONNECTORS,
            category=ToolCategory.ACTION,
            input_model=AppArgs,
            handler=disconnect_app,
            timeout_seconds=30,
            acl=writer,
            preview=disconnect_preview,
            irreversible=True,
        ),
    ]


def _writer_required(directory: WorkspaceDirectory) -> AclCheck:
    """data-pipeline lets viewers look at connections but not change them; say so before anyone is asked."""

    async def check(ctx: AgentContext, args: ToolInput) -> None:
        role = await directory.role_in(ctx.user_id, ctx.tenant_id)
        if role is None:
            raise ToolAccessDenied("you are no longer a member of this workspace")
        if role == "VIEWER":
            raise ToolAccessDenied("viewers can't change connected apps in this workspace")

    return check


# ----------------------------------------------------------------------------- state


def _state(status: dict[str, Any], connected: bool | None) -> str:
    """not connected | reconnect needed | needs setup | syncing | last sync failed | connected."""
    name = str(status.get("status") or "")
    if connected is None:
        connected = name not in ("", "Available", "Disconnected")
    if not connected:
        return "not connected"
    if "reconnect" in str(status.get("current_progress") or "").lower():
        return "reconnect needed"
    if name in ("", "Available", "Disconnected", "Configuration Required"):
        return "needs setup"
    if name == "Syncing" or bool((status.get("lock") or {}).get("is_locked")):
        return "syncing"
    if name in ("Failed", "Sync Failed"):
        return "last sync failed"
    return "connected"


def _require_syncable(app: App, state: str) -> None:
    if state in ("connected", "last sync failed"):
        return
    if state == "syncing":
        raise ToolInputError(f"a {app.name} sync is already running; check get_app_sync_history in a minute")
    raise ToolInputError(_not_ready(app, state))


def _require_configurable(app: App, state: str) -> None:
    if state in ("connected", "last sync failed", "needs setup"):
        return
    if state == "syncing":
        raise ToolInputError(f"{app.name} is syncing; change its settings once the sync has finished")
    raise ToolInputError(_not_ready(app, state))


def _require_schedulable(app: App, state: str, schedule: str) -> None:
    if schedule == "off" or state in ("connected", "last sync failed", "syncing"):
        return
    raise ToolInputError(_not_ready(app, state))


def _not_ready(app: App, state: str) -> str:
    if state == "needs setup":
        return (
            f"{app.name} is connected but not set up in this workspace: the rep chooses what it syncs on the Connectors "
            f"page ({CONNECTORS_PAGE}), or you can change its sync settings"
        )
    if state == "reconnect needed":
        return f"{app.name} needs to be connected again: the rep does that on the Connectors page ({CONNECTORS_PAGE})"
    return f"{app.name} isn't connected: the rep connects it on the Connectors page ({CONNECTORS_PAGE}), in a browser"


# ----------------------------------------------------------------------------- settings


_SETTING_FIELDS = ("max_per_sync", "window_days", "categories", "future_window_days")


def _config_field(app: App, field: str) -> str:
    return {"max_per_sync": app.max_field, "window_days": "sync_window_days"}.get(field, field)


def _setting(config: dict[str, Any], app: App, field: str) -> Any:
    value = config.get(_config_field(app, field))
    if field == "categories":
        return [str(item).upper() for item in value or []]
    return value


def _full_config(app: App, config: dict[str, Any]) -> dict[str, Any]:
    """The configuration as data-pipeline takes it back: every field, so nothing falls back to a default."""
    body = {
        app.max_field: config.get(app.max_field),
        "categories": list(config.get("categories") or []),
        "sync_window_days": config.get("sync_window_days"),
        "auto_sync_interval_minutes": config.get("auto_sync_interval_minutes") or 0,
        "sync_frequency": config.get("sync_frequency") or "off",
        "auto_sync_enabled": bool(config.get("auto_sync_enabled")),
        "webhook_enabled": bool(config.get("webhook_enabled")),
    }
    if app.source == "calendar":
        body["future_window_days"] = config.get("future_window_days")
    return {key: value for key, value in body.items() if value is not None}


def plan_settings(app: App, args: SyncSettingsArgs, config: dict[str, Any]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """(the changes, as the rep sees them; the whole configuration to save)."""
    changes = []
    for field in _SETTING_FIELDS:
        wanted = getattr(args, field)
        if wanted is None:
            continue
        before = _setting(config, app, field)
        if before != wanted:
            changes.append({"field": field, "before": before, "after": wanted})
    body = _full_config(app, config) | {_config_field(app, change["field"]): change["after"] for change in changes}
    return changes, body


def _describe(change: dict[str, Any]) -> str:
    label = {"max_per_sync": "per sync", "window_days": "days back", "categories": "syncs", "future_window_days": "days ahead"}[change["field"]]

    def show(value: Any) -> str:
        return ", ".join(value).lower().replace("_", " ") if isinstance(value, list) else ("—" if value is None else str(value))

    return f"{label} {show(change['before'])} → {show(change['after'])}"


# ----------------------------------------------------------------------------- views


def _schedule(config: dict[str, Any]) -> str:
    minutes = int(config.get("auto_sync_interval_minutes") or 0)
    if not config.get("auto_sync_enabled") or str(config.get("sync_frequency") or "off") in ("off", "manual"):
        return "off"
    for name, (_, schedule_minutes) in SCHEDULES.items():
        if schedule_minutes and schedule_minutes == minutes:
            return name
    return f"every {minutes} minutes" if minutes else "on changes only"


def _minutes(schedule: str) -> int:
    digits = "".join(character for character in schedule if character.isdigit())
    return int(digits) if digits else 0


def _synced(status: dict[str, Any]) -> int:
    return int((status.get("backfill_state") or {}).get("total_synced_so_far") or 0)


def _view(key: str, app: App, status: dict[str, Any], connected: bool | None) -> dict[str, Any]:
    state = _state(status, connected)
    view: dict[str, Any] = {"app": key, "name": app.name, "state": state}
    if state == "not connected":
        return view
    config = status.get("config") or {}
    syncs: dict[str, Any] = {"up_to": config.get(app.max_field), "unit": app.unit, "days_back": config.get("sync_window_days")}
    if app.categories:
        syncs["what"] = [str(item).upper() for item in config.get("categories") or []]
    if app.source == "calendar":
        syncs["days_ahead"] = config.get("future_window_days")
    view |= {
        "auto_sync": _schedule(config),
        "syncs": syncs,
        "items_synced": _synced(status),
        "last_sync_attempt": status.get("last_successful_sync_at"),
    }
    progress = clip(status.get("current_progress"), 160)
    if progress:
        view["note"] = progress
    return view


def _brief(view: dict[str, Any]) -> str:
    if view["state"] == "not connected":
        return f"{view['name']}: not connected"
    return f"{view['name']}: {view['state']}, auto-sync {view['auto_sync']}, {view['items_synced']} synced"


def _sync_view(activity: dict[str, Any]) -> dict[str, Any]:
    metrics = activity.get("metrics") or {}
    failures = [
        {"item": clip(item.get("subject") or item.get("name") or item.get("filename") or item.get("summary"), 120), "error": clip(item.get("error_message"), 200)}
        for item in activity.get("items") or []
        if isinstance(item, dict) and str(item.get("status") or "").upper() == "FAILED"
    ][:5]
    return {
        "trigger": _TRIGGERS.get(str(activity.get("trigger_type") or ""), str(activity.get("trigger_type") or "").lower()),
        "status": str(activity.get("status") or "").lower().replace("_", " "),
        "started_at": activity.get("started_at"),
        "completed_at": activity.get("completed_at"),
        "found": int(metrics.get("total_discovered") or 0),
        "added": int(metrics.get("succeeded") or 0),
        "skipped": int(metrics.get("skipped") or 0),
        "failed": int(metrics.get("failed") or 0),
        "failed_items": failures,
    }
