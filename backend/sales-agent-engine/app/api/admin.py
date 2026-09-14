"""Super Admin Console API (``/admin/...``): platform-wide agent overview, usage, sessions, controls,
tools, model routes and rates, prompts and the audit log. Every route requires a platform super admin
(``app.admin.guard``). The response shapes mirror ``frontend/src/api/adminApi.ts``."""

from __future__ import annotations

import asyncio
import logging
import time
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Annotated, Any, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Path, Query, Request
from pydantic import BaseModel, ConfigDict, Field

from app.admin.guard import AdminActor
from app.admin.runtime import (
    LIMIT_BOUNDS,
    PROTECTED_TOOLS,
    PROVIDERS,
    ROUTES,
    AdminRuntime,
    compose_prompt,
    rate_key,
)
from app.admin.store import UsageRow
from app.api.deps import ContainerDep, get_container, get_principal
from app.container import Container
from app.core.clock import utcnow
from app.core.enums import PendingActionStatus, SessionStatus
from app.core.errors import Conflict, NotFound, ValidationFailed
from app.engine.delegation import SUBAGENTS
from app.engine.events import EventType, emit_best_effort
from app.engine.orchestrator import BASE_PROMPT, _time_context
from app.engine.runner import context_for
from app.tools.registry import SCOPES


async def require_super_admin(request: Request, container: Annotated[Container, Depends(get_container)]) -> AdminActor:
    principal = await get_principal(request, container)
    return await container.admin_guard.require_super_admin(principal)


ActorDep = Annotated[AdminActor, Depends(require_super_admin)]

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin", tags=["admin"], dependencies=[Depends(require_super_admin)])


class _Body(BaseModel):
    model_config = ConfigDict(extra="forbid")


# ============================================================================ usage helpers
def _day(value: datetime) -> str:
    return value.date().isoformat()


def _days(since: datetime, count: int) -> list[str]:
    return [(since + timedelta(days=offset)).date().isoformat() for offset in range(count)]


class _Tally:
    __slots__ = ("calls", "input_tokens", "output_tokens", "cost_usd", "sessions", "users", "unpriced")

    def __init__(self) -> None:
        self.calls = 0
        self.input_tokens = 0
        self.output_tokens = 0
        self.cost_usd = 0.0
        self.sessions: set[UUID] = set()
        self.users: set[UUID] = set()
        self.unpriced = 0

    def add(self, row: UsageRow, cost: float, priced: bool) -> None:
        self.calls += row.calls
        self.input_tokens += row.input_tokens
        self.output_tokens += row.output_tokens
        self.cost_usd += cost
        if row.session_id:
            self.sessions.add(row.session_id)
        if row.user_id:
            self.users.add(row.user_id)
        if not priced:
            self.unpriced += row.calls

    def tokens(self) -> dict[str, Any]:
        return {
            "calls": self.calls,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "cost_usd": round(self.cost_usd, 6),
        }


def _cost(admin: AdminRuntime, provider: str, model: str, calls: int, tokens_in: int, tokens_out: int) -> tuple[float, bool]:
    rate = admin.price(provider, model)
    if rate is None:
        return 0.0, False
    cost = (
        tokens_in / 1_000_000 * float(rate["input_per_million_usd"])
        + tokens_out / 1_000_000 * float(rate["output_per_million_usd"])
        + calls * float(rate.get("request_fee_usd") or 0)
    )
    return cost, True


def _by(rows: list[UsageRow], admin: AdminRuntime, key) -> dict[Any, _Tally]:
    tallies: dict[Any, _Tally] = defaultdict(_Tally)
    for row in rows:
        cost, priced = _cost(admin, row.provider, row.model, row.calls, row.input_tokens, row.output_tokens)
        tallies[key(row)].add(row, cost, priced)
    return tallies


def _start_of_day(value: datetime) -> datetime:
    return value.replace(hour=0, minute=0, second=0, microsecond=0)


def _providers(container: Container) -> list[dict[str, Any]]:
    configured = container.router.configured_providers()
    settings = container.settings
    return [
        {"name": name, "label": label, "configured": name in configured, "supports_model_list": supports}
        for name, (label, supports) in PROVIDERS.items()
    ] + [
        {
            "name": "tavily",
            "label": "Tavily web search",
            "configured": bool(settings.tavily_api_key and settings.tavily_api_key.get_secret_value()),
            "supports_model_list": False,
        },
        {
            "name": "composio",
            "label": "Composio connected apps",
            "configured": bool(settings.composio_api_key and settings.composio_api_key.get_secret_value()),
            "supports_model_list": False,
        },
    ]


# ============================================================================ overview + usage
@router.get("/overview")
async def overview(container: ContainerDep) -> dict[str, Any]:
    admin = container.admin
    now = utcnow()
    since = _start_of_day(now) - timedelta(days=13)
    rows, started, counts = await asyncio.gather(
        admin.store.usage_rows(since), admin.store.sessions_started(since), admin.store.status_counts()
    )
    days = _days(since, 14)
    by_day = _by(rows, admin, lambda row: row.day)
    sessions_by_day: dict[str, int] = defaultdict(int)
    for day, _, _, _ in started:
        sessions_by_day[day] += 1
    today = _day(now)
    today_tally = by_day.get(today, _Tally())
    workspaces = {row.tenant_id for row in rows if row.day == today and row.tenant_id} | {t for d, t, _, _ in started if d == today}
    users = {row.user_id for row in rows if row.day == today and row.user_id} | {u for d, _, u, _ in started if d == today}
    return {
        "agent_enabled": admin.agent_enabled,
        "maintenance_message": admin.maintenance_message,
        "running_sessions": counts.get(SessionStatus.RUNNING, 0),
        "awaiting_approval": counts.get(SessionStatus.AWAITING_APPROVAL, 0),
        "today": {
            **today_tally.tokens(),
            "sessions_started": sessions_by_day.get(today, 0),
            "active_workspaces": len(workspaces),
            "active_users": len(users),
        },
        "daily": [
            {**by_day.get(day, _Tally()).tokens(), "date": day, "sessions": sessions_by_day.get(day, 0)} for day in days
        ],
        "providers": [{k: v for k, v in item.items() if k != "supports_model_list"} for item in _providers(container)],
    }


@router.get("/usage")
async def usage(container: ContainerDep, days: Annotated[int, Query(ge=1, le=365)] = 30) -> dict[str, Any]:
    admin = container.admin
    now = utcnow()
    since = _start_of_day(now) - timedelta(days=days - 1)
    rows, started, outcomes = await asyncio.gather(
        admin.store.usage_rows(since), admin.store.sessions_started(since), admin.store.tool_outcomes(since)
    )
    total = _by(rows, admin, lambda row: "all").get("all", _Tally())
    sessions_by_day: dict[str, int] = defaultdict(int)
    for day, _, _, _ in started:
        sessions_by_day[day] += 1
    by_day = _by(rows, admin, lambda row: row.day)

    tools: dict[str, dict[str, int]] = defaultdict(lambda: {"calls": 0, "executed": 0, "failed": 0, "denied": 0, "rejected": 0, "other": 0})
    for tool, outcome, count in outcomes:
        entry = tools[tool]
        entry["calls"] += count
        bucket = {"EXECUTED": "executed", "FAILED": "failed", "UNKNOWN": "failed", "DENIED": "denied", "REJECTED": "rejected"}
        entry[bucket.get(outcome, "other")] += count

    by_model = _by(rows, admin, lambda row: (row.provider, row.model))
    return {
        "from": since.isoformat(),
        "to": now.isoformat(),
        "totals": {
            **total.tokens(),
            "unpriced_calls": total.unpriced,
            "sessions": len(total.sessions | {sid for _, _, _, sid in started}),
            "workspaces": len({row.tenant_id for row in rows if row.tenant_id} | {t for _, t, _, _ in started}),
            "users": len({row.user_id for row in rows if row.user_id} | {u for _, _, u, _ in started}),
            "tool_calls": sum(entry["calls"] for entry in tools.values()),
        },
        "daily": [
            {**by_day.get(day, _Tally()).tokens(), "date": day, "sessions": sessions_by_day.get(day, 0)}
            for day in _days(since, days)
        ],
        "by_model": sorted(
            (
                {**tally.tokens(), "provider": provider, "model": model, "priced": admin.price(provider, model) is not None}
                for (provider, model), tally in by_model.items()
            ),
            key=lambda item: -item["cost_usd"],
        ),
        "by_purpose": sorted(
            ({**tally.tokens(), "purpose": purpose} for purpose, tally in _by(rows, admin, lambda row: row.purpose).items()),
            key=lambda item: -item["calls"],
        ),
        "by_workspace": sorted(
            (
                {**tally.tokens(), "workspace_id": str(tenant), "sessions": len(tally.sessions), "users": len(tally.users)}
                for tenant, tally in _by(rows, admin, lambda row: row.tenant_id).items()
                if tenant is not None
            ),
            key=lambda item: -item["cost_usd"],
        ),
        "by_user": sorted(
            (
                {**tally.tokens(), "user_id": str(user), "sessions": len(tally.sessions)}
                for user, tally in _by(rows, admin, lambda row: row.user_id).items()
                if user is not None
            ),
            key=lambda item: -item["cost_usd"],
        ),
        "tools": sorted(({"tool": tool, **entry} for tool, entry in tools.items()), key=lambda item: -item["calls"]),
    }


# ============================================================================ sessions
@router.get("/sessions")
async def sessions(
    container: ContainerDep,
    status: Annotated[SessionStatus | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
) -> list[dict[str, Any]]:
    admin = container.admin
    rows = await admin.store.list_sessions(status, limit)
    ids = [row.id for row in rows]
    usage_by_session, tool_calls, stopping = await asyncio.gather(
        admin.store.session_usage(ids), admin.store.session_tool_calls(ids), admin.stop_requested(ids)
    )
    result = []
    for row in rows:
        tokens = 0
        cost = 0.0
        for provider, model, calls, tokens_in, tokens_out in usage_by_session.get(row.id, []):
            tokens += tokens_in + tokens_out
            cost += _cost(admin, provider, model, calls, tokens_in, tokens_out)[0]
        result.append(
            {
                "id": str(row.id),
                "workspace_id": str(row.tenant_id),
                "user_id": str(row.user_id),
                "status": row.status,
                "mode": row.mode,
                "turns": row.turn,
                "started_at": row.started_at.isoformat(),
                "ended_at": row.ended_at.isoformat() if row.ended_at else None,
                "updated_at": row.updated_at.isoformat() if row.updated_at else None,
                "tokens": tokens,
                "cost_usd": round(cost, 6),
                "tool_calls": tool_calls.get(row.id, 0),
                "stop_requested": row.id in stopping,
            }
        )
    return result


@router.post("/sessions/{session_id}/stop")
async def stop_session(session_id: UUID, actor: ActorDep, container: ContainerDep) -> dict[str, Any]:
    admin = container.admin
    row = await admin.store.get_session(session_id)
    if row is None:
        raise NotFound("session not found")
    if row.status not in (SessionStatus.RUNNING, SessionStatus.AWAITING_APPROVAL):
        raise Conflict("this request has already finished")
    await admin.request_stop(row.id)
    if row.status == SessionStatus.AWAITING_APPROVAL:
        expired = await admin.store.expire_session_approvals(row.id, actor)
        for action in expired:
            await emit_best_effort(
                container.events,
                row.id,
                EventType.APPROVAL_RESOLVED,
                {"pending_action_id": action.id, "status": PendingActionStatus.EXPIRED, "resolved_by": actor.user_id},
            )
        if expired:
            # The run wakes on the expired decision; its next step sees the stop and ends the request.
            try:
                await container.runner.resume(
                    context_for(row), {"pending_action_id": str(expired[-1].id), "status": PendingActionStatus.EXPIRED}
                )
            except Exception:  # the decision is saved: the maintenance sweep resumes the session
                logger.exception("could not resume session %s after an admin stop", row.id)
    await admin.store.audit(
        actor,
        action="session.stopped",
        target_type="session",
        target_id=str(row.id),
        target_label=row.title,
        summary=f"Stopped a {row.status.lower().replace('_', ' ')} agent request in workspace {row.tenant_id}",
    )
    return {"id": str(row.id), "status": row.status, "stop_requested": True}


# ============================================================================ controls
class ControlsInput(_Body):
    agent_enabled: bool
    maintenance_message: str | None = Field(default=None, max_length=500)
    sub_agents_enabled: bool
    web_search_enabled: bool
    limits: dict[str, int | None] = Field(default_factory=dict)


def _controls_view(admin: AdminRuntime) -> dict[str, Any]:
    record = admin.snapshot.controls
    return {
        "agent_enabled": admin.agent_enabled,
        "maintenance_message": admin.maintenance_message,
        "sub_agents_enabled": admin.sub_agents_enabled,
        "web_search_enabled": admin.web_search_enabled,
        "limits": {
            key: {
                "value": admin.limit(key),
                "default": admin.default_limit(key),
                "overridden": admin.limit_override(key) is not None,
                "min": low,
                "max": high,
            }
            for key, (low, high) in LIMIT_BOUNDS.items()
        },
        "version": record.version if record else 0,
        "updated_at": record.updated_at.isoformat() if record and record.updated_at else None,
        "updated_by_email": record.updated_by_email if record else None,
    }


@router.get("/controls")
async def get_controls(container: ContainerDep) -> dict[str, Any]:
    return _controls_view(container.admin)


@router.put("/controls")
async def save_controls(body: ControlsInput, actor: ActorDep, container: ContainerDep) -> dict[str, Any]:
    admin = container.admin
    unknown = sorted(set(body.limits) - set(LIMIT_BOUNDS))
    if unknown:
        raise ValidationFailed(f"unknown limits: {', '.join(unknown)}")
    limits: dict[str, int] = {}
    for key, value in body.limits.items():
        if value is None:
            continue
        low, high = LIMIT_BOUNDS[key]
        if not low <= value <= high:
            raise ValidationFailed(f"{key} must be between {low} and {high}")
        limits[key] = value
    before = _controls_view(admin)
    value = {
        "agent_enabled": body.agent_enabled,
        "maintenance_message": (body.maintenance_message or "").strip() or None,
        "sub_agents_enabled": body.sub_agents_enabled,
        "web_search_enabled": body.web_search_enabled,
        "limits": limits,
    }
    await admin.store.save_setting("controls", value, actor)
    await admin.refresh()

    changes = []
    if before["agent_enabled"] != body.agent_enabled:
        changes.append("resumed the agent" if body.agent_enabled else "paused the agent for every workspace")
    for flag, label in (("sub_agents_enabled", "sub-agents"), ("web_search_enabled", "web search")):
        if before[flag] != value[flag]:
            changes.append(f"turned {label} {'on' if value[flag] else 'off'}")
    if before["maintenance_message"] != value["maintenance_message"]:
        changes.append("changed the maintenance message")
    for key in LIMIT_BOUNDS:
        old = before["limits"][key]["value"] if before["limits"][key]["overridden"] else None
        if old != limits.get(key):
            changes.append(f"set {key} to {limits[key]}" if key in limits else f"reset {key} to the default")
    if before["agent_enabled"] != body.agent_enabled:
        action = "agent.resumed" if body.agent_enabled else "agent.paused"
    else:
        action = "agent.controls_updated"
    summary = "; ".join(changes) or "saved the agent controls without changes"
    await admin.store.audit(actor, action=action, target_type="agent_controls", target_label="Agent controls", summary=summary[:1].upper() + summary[1:])
    return _controls_view(admin)


# ============================================================================ tools
class ToolInput(_Body):
    enabled: bool


def _tool_view(container: Container, definition, stats: dict[str, tuple[int, int]]) -> dict[str, Any]:
    admin = container.admin
    calls, failures = stats.get(definition.name, (0, 0))
    return {
        "name": definition.name,
        "description": definition.description,
        "kind": definition.kind.value,
        "scope": definition.scope.value,
        "category": definition.category.value,
        "enabled": definition.name not in admin.explicitly_disabled(),
        "protected": definition.name in PROTECTED_TOOLS,
        "irreversible": definition.irreversible,
        "available_to": [agent for agent, scopes in SCOPES.items() if definition.scope in scopes],
        "calls_30d": calls,
        "failures_30d": failures,
    }


async def _tool_stats(container: Container) -> dict[str, tuple[int, int]]:
    stats: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    for tool, outcome, count in await container.admin.store.tool_outcomes(utcnow() - timedelta(days=30)):
        stats[tool][0] += count
        if outcome in ("FAILED", "UNKNOWN"):
            stats[tool][1] += count
    return {tool: (calls, failures) for tool, (calls, failures) in stats.items()}


@router.get("/tools")
async def list_tools(container: ContainerDep) -> list[dict[str, Any]]:
    stats = await _tool_stats(container)
    return [_tool_view(container, d, stats) for d in sorted(container.registry.all(), key=lambda d: d.name)]


@router.put("/tools/{name}")
async def set_tool(name: str, body: ToolInput, actor: ActorDep, container: ContainerDep) -> dict[str, Any]:
    admin = container.admin
    definition = container.registry.get(name)
    if definition is None:
        raise NotFound("tool not found")
    if name in PROTECTED_TOOLS and not body.enabled:
        raise Conflict("this tool keeps the agent safe and can't be turned off")
    disabled = set(admin.explicitly_disabled())
    was_enabled = name not in disabled
    if body.enabled:
        disabled.discard(name)
    else:
        disabled.add(name)
    await admin.store.save_setting("tools", {"disabled": sorted(disabled)}, actor)
    await admin.refresh()
    if was_enabled != body.enabled:
        await admin.store.audit(
            actor,
            action="tool.enabled" if body.enabled else "tool.disabled",
            target_type="tool",
            target_id=name,
            target_label=name,
            summary=f"Turned the {name} tool {'on' if body.enabled else 'off'} for every workspace",
        )
    return _tool_view(container, definition, await _tool_stats(container))


router.add_api_route("/tools/{name}", set_tool, methods=["PATCH"], operation_id="admin_patch_tool")


# ============================================================================ models
RouteName = Literal["complex", "simple", "failover", "web_grounded"]


class RouteInput(_Body):
    provider: str | None = None
    models: list[str] | None = None
    reset: bool = False


class RateInput(_Body):
    provider: str = Field(min_length=1, max_length=50)
    model: str = Field(min_length=1, max_length=300)
    input_per_million_usd: float = Field(ge=0, le=1000)
    output_per_million_usd: float = Field(ge=0, le=1000)
    request_fee_usd: float = Field(default=0, ge=0, le=1000)


class RatesInput(_Body):
    rates: list[RateInput] = Field(max_length=200)


class ModelTestInput(_Body):
    provider: str = Field(min_length=1, max_length=50)
    model: str = Field(min_length=1, max_length=300)


async def _models_view(container: Container) -> dict[str, Any]:
    admin = container.admin
    configured = container.router.configured_providers()
    routes = []
    for name, (label, description) in ROUTES.items():
        current, default = admin.route(name), admin.default_route(name)
        routes.append(
            {
                "route": name,
                "label": label,
                "description": description,
                "provider": current.provider if current else "",
                "models": list(current.models) if current else [],
                "default_provider": default.provider if default else "",
                "default_models": list(default.models) if default else [],
                "overridden": admin.route_override(name) is not None,
                "available": bool(current and current.provider in configured),
            }
        )
    rows = await admin.store.usage_rows(_start_of_day(utcnow()) - timedelta(days=6))
    usage_7d = sorted(
        (
            {**tally.tokens(), "provider": provider, "model": model}
            for (provider, model), tally in _by(rows, admin, lambda row: (row.provider, row.model)).items()
        ),
        key=lambda item: -item["calls"],
    )
    return {
        "routes": routes,
        "providers": [item for item in _providers(container) if item["name"] in PROVIDERS],
        "rates": admin.rates(),
        "usage_7d": usage_7d,
    }


@router.get("/models")
async def models(container: ContainerDep) -> dict[str, Any]:
    return await _models_view(container)


@router.put("/models/routes/{route}")
async def set_route(
    route: Annotated[RouteName, Path()], body: RouteInput, actor: ActorDep, container: ContainerDep
) -> dict[str, Any]:
    admin = container.admin
    overrides = dict(admin.snapshot.routes.value) if admin.snapshot.routes else {}
    label = ROUTES[route][0]
    if body.reset:
        overrides.pop(route, None)
        summary = f"Reset the {label} route to the server default"
    else:
        provider = (body.provider or "").strip().lower()
        models = [model.strip() for model in body.models or [] if model and model.strip()]
        if provider not in PROVIDERS:
            raise ValidationFailed(f"unknown provider '{body.provider}'")
        if not models or len(models) > 5 or any(len(model) > 200 for model in models):
            raise ValidationFailed("give between 1 and 5 model names")
        if not PROVIDERS[provider][1] and len(models) != 1:
            raise ValidationFailed(f"{PROVIDERS[provider][0]} uses one model per route")
        if route == "web_grounded" and provider != "gemini":
            raise ValidationFailed("only Gemini can ground answers in Google Search")
        overrides[route] = {"provider": provider, "models": models}
        summary = f"Set the {label} route to {', '.join(models)} on {PROVIDERS[provider][0]}"
    await admin.store.save_setting("routes", overrides, actor)
    await admin.refresh()
    await admin.store.audit(actor, action="model.route_updated", target_type="model_route", target_id=route, target_label=label, summary=summary)
    return await _models_view(container)


@router.put("/models/rates")
async def save_rates(body: RatesInput, actor: ActorDep, container: ContainerDep) -> dict[str, Any]:
    admin = container.admin
    seen: set[tuple[str, str]] = set()
    rates = []
    for rate in body.rates:
        provider = rate.provider.strip().lower()
        if provider not in PROVIDERS:
            raise ValidationFailed(f"unknown provider '{rate.provider}'")
        key = rate_key(provider, rate.model)
        if key in seen:
            raise ValidationFailed(f"{rate.model} on {provider} is listed twice")
        seen.add(key)
        rates.append({**rate.model_dump(), "provider": provider, "model": rate.model.strip()})
    await admin.store.save_setting("rates", {"rates": rates}, actor)
    await admin.refresh()
    await admin.store.audit(
        actor,
        action="model.rates_updated",
        target_type="model_rates",
        target_label="Model rates",
        summary=f"Saved {len(rates)} custom model rate{'s' if len(rates) != 1 else ''}",
    )
    return await _models_view(container)


@router.post("/models/test")
async def test_model(body: ModelTestInput, container: ContainerDep) -> dict[str, Any]:
    provider, model = body.provider.strip().lower(), body.model.strip()
    started = time.monotonic()
    result: dict[str, Any] = {"ok": False, "provider": provider, "model": model, "reply": None, "input_tokens": 0, "output_tokens": 0, "error": None}
    try:
        completion = await asyncio.wait_for(
            container.router.test_model(provider, model, "Reply with the single word OK.", max_output_tokens=256), timeout=60
        )
        result |= {
            "ok": True,
            "model": completion.model or model,
            "reply": completion.message.content.strip(),
            "input_tokens": completion.usage.input_tokens,
            "output_tokens": completion.usage.output_tokens,
        }
    except TimeoutError:
        result["error"] = "the model did not answer within 60 seconds"
    except Exception as exc:
        result["error"] = f"{type(exc).__name__}: {exc}"[:500]
    result["latency_ms"] = int((time.monotonic() - started) * 1000)
    return result


# ============================================================================ prompts
PromptAgentName = Literal["orchestrator", "research", "outreach", "quote"]
PROMPT_MAX_CHARS = 20_000
REPLACE_MIN_CHARS = 50

PROMPT_INFO: dict[str, tuple[str, str]] = {
    "orchestrator": ("Sales assistant", "The coordinator every rep talks to: plans, uses tools and hands work to sub-agents."),
    "research": ("Research agent", SUBAGENTS["research"].purpose),
    "outreach": ("Outreach agent", SUBAGENTS["outreach"].purpose),
    "quote": ("Quote agent", SUBAGENTS["quote"].purpose),
}


def _base_prompt(agent: str) -> str:
    return BASE_PROMPT if agent == "orchestrator" else SUBAGENTS[agent].prompt.strip()


class PromptInput(_Body):
    mode: Literal["APPEND", "REPLACE"]
    instructions: str = Field(max_length=PROMPT_MAX_CHARS)
    note: str | None = Field(default=None, max_length=500)


class PreviewInput(_Body):
    agent: PromptAgentName
    mode: Literal["APPEND", "REPLACE"]
    instructions: str = Field(max_length=PROMPT_MAX_CHARS)


def _version_view(row, active_version: int | None) -> dict[str, Any]:
    return {
        "version": row.version,
        "mode": row.mode,
        "instructions": row.instructions,
        "note": row.note,
        "created_at": row.created_at.isoformat(),
        "created_by_email": row.created_by_email,
        "active": row.version == active_version,
    }


async def _prompts_view(container: Container) -> list[dict[str, Any]]:
    grouped = await container.admin.store.prompt_versions()
    result = []
    for agent, (title, description) in PROMPT_INFO.items():
        versions = grouped.get(agent, [])
        active = versions[0].version if versions else None
        result.append(
            {
                "agent": agent,
                "title": title,
                "description": description,
                "base_prompt": _base_prompt(agent),
                "active": _version_view(versions[0], active) if versions else None,
                "versions": [_version_view(row, active) for row in versions],
            }
        )
    return result


async def _prompt_view(container: Container, agent: str) -> dict[str, Any]:
    return next(item for item in await _prompts_view(container) if item["agent"] == agent)


@router.get("/prompts")
async def prompts(container: ContainerDep) -> list[dict[str, Any]]:
    return await _prompts_view(container)


@router.post("/prompts/preview")
async def preview_prompt(body: PreviewInput) -> dict[str, str]:
    body_text = compose_prompt(_base_prompt(body.agent), body.mode, body.instructions)
    return {"system_prompt": f"{body_text}\n\n{_time_context(None)}"}


@router.get("/prompts/{agent}")
async def prompt(agent: Annotated[PromptAgentName, Path()], container: ContainerDep) -> dict[str, Any]:
    return await _prompt_view(container, agent)


@router.post("/prompts/{agent}")
async def publish_prompt(
    agent: Annotated[PromptAgentName, Path()], body: PromptInput, actor: ActorDep, container: ContainerDep
) -> dict[str, Any]:
    if body.mode == "REPLACE" and len(body.instructions.strip()) < REPLACE_MIN_CHARS:
        raise ValidationFailed(f"a replacement prompt needs at least {REPLACE_MIN_CHARS} characters")
    admin = container.admin
    row = await admin.store.publish_prompt(
        agent, mode=body.mode, instructions=body.instructions, note=(body.note or "").strip() or None, actor=actor
    )
    await admin.refresh()
    title = PROMPT_INFO[agent][0]
    what = "replaced" if body.mode == "REPLACE" else ("cleared the additions to" if not body.instructions.strip() else "added to")
    await admin.store.audit(
        actor,
        action="prompt.published",
        target_type="prompt",
        target_id=agent,
        target_label=title,
        summary=f"Published version {row.version} of the {title} prompt ({what} the built-in prompt)",
    )
    return await _prompt_view(container, agent)


router.add_api_route("/prompts/{agent}", publish_prompt, methods=["PUT"], operation_id="admin_put_prompt")


@router.post("/prompts/{agent}/versions/{version}/restore")
async def restore_prompt(
    agent: Annotated[PromptAgentName, Path()],
    version: Annotated[int, Path(ge=1)],
    actor: ActorDep,
    container: ContainerDep,
) -> dict[str, Any]:
    admin = container.admin
    old = await admin.store.prompt_version(agent, version)
    if old is None:
        raise NotFound("prompt version not found")
    row = await admin.store.publish_prompt(
        agent, mode=old.mode, instructions=old.instructions, note=f"Restored from version {version}", actor=actor
    )
    await admin.refresh()
    title = PROMPT_INFO[agent][0]
    await admin.store.audit(
        actor,
        action="prompt.restored",
        target_type="prompt",
        target_id=agent,
        target_label=title,
        summary=f"Restored version {version} of the {title} prompt as version {row.version}",
    )
    return await _prompt_view(container, agent)


# ============================================================================ audit
@router.get("/audit")
async def audit(container: ContainerDep, limit: Annotated[int, Query(ge=1, le=500)] = 100) -> list[dict[str, Any]]:
    rows = await container.admin.store.list_audit(limit)
    return [
        {
            "id": str(row.id),
            "service": "agent",
            "actor_user_id": str(row.actor_user_id),
            "actor_email": row.actor_email,
            "action": row.action,
            "target_type": row.target_type,
            "target_id": row.target_id,
            "target_label": row.target_label,
            "summary": row.summary,
            "created_at": row.created_at.isoformat(),
        }
        for row in rows
    ]
