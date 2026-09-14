"""Super Admin Console: the platform super admin guard, the overrides runtime and a few endpoints (with fakes)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any
from uuid import UUID, uuid4

import httpx
import pytest
from fastapi import FastAPI

from app.admin.guard import NotSuperAdmin, PlatformAccessClient, PlatformAdminGuard
from app.admin.runtime import AdminRuntime, AdminSnapshot, SettingRecord, compose_prompt
from app.api import admin as admin_api
from app.api.errors import install_error_handlers
from app.core.context import Principal
from app.core.errors import AuthenticationFailed, UpstreamUnavailable
from app.engine.orchestrator import BASE_PROMPT
from app.models.router import ModelRouter, Route, RoutingRules
from app.observability.tracing import NoopTracingClient
from app.tools.registry import AgentScopes, ToolDefinition, ToolRegistry
from app.tools.types import ToolCategory, ToolInput, ToolKind, ToolOutput, ToolScope

ADMIN = uuid4()
REP = uuid4()


# ----------------------------------------------------------------------------- fakes
class AuthService:
    def __init__(self) -> None:
        self.calls = 0
        self.down = False

    def transport(self) -> httpx.MockTransport:
        def handler(request: httpx.Request) -> httpx.Response:
            self.calls += 1
            if self.down:
                raise httpx.ConnectError("auth-service unreachable", request=request)
            assert request.headers["X-Internal-Token"] == "secret"
            user_id = UUID(request.url.path.split("/")[-2])
            return httpx.Response(
                200, json={"authUserId": str(user_id), "superAdmin": user_id == ADMIN, "email": "boss@rolesync.test"}
            )

        return httpx.MockTransport(handler)


def make_guard(auth: AuthService, *, token: str | None = "secret", now: list[float] | None = None) -> PlatformAdminGuard:
    clock = now or [0.0]
    client = PlatformAccessClient(base_url="http://auth.test", token=token, http=httpx.AsyncClient(transport=auth.transport()))
    return PlatformAdminGuard(client, ttl_seconds=30, clock=lambda: clock[0])


@dataclass
class FakeStore:
    settings: dict[str, SettingRecord] = field(default_factory=dict)
    audits: list[dict[str, Any]] = field(default_factory=list)
    prompts: list[Any] = field(default_factory=list)

    async def load_snapshot(self) -> AdminSnapshot:
        latest: dict[str, Any] = {}
        for row in self.prompts:
            if row.agent not in latest or row.version > latest[row.agent].version:
                latest[row.agent] = row
        snapshot = AdminSnapshot(prompts={agent: (row.mode, row.instructions) for agent, row in latest.items()})
        for key, record in self.settings.items():
            setattr(snapshot, key, record)
        return snapshot

    async def save_setting(self, key: str, value: dict[str, Any], actor: Any) -> SettingRecord:
        version = self.settings[key].version + 1 if key in self.settings else 1
        self.settings[key] = SettingRecord(value, version, datetime.now(UTC), actor.email)
        return self.settings[key]

    async def audit(self, actor: Any, **entry: Any) -> None:
        self.audits.append({"actor": actor.user_id, **entry})

    async def prompt_versions(self) -> dict[str, list[Any]]:
        grouped: dict[str, list[Any]] = {}
        for row in sorted(self.prompts, key=lambda r: -r.version):
            grouped.setdefault(row.agent, []).append(row)
        return grouped

    async def publish_prompt(self, agent: str, *, mode: str, instructions: str, note: str | None, actor: Any) -> Any:
        version = 1 + max((row.version for row in self.prompts if row.agent == agent), default=0)
        row = SimpleNamespace(
            agent=agent, version=version, mode=mode, instructions=instructions, note=note,
            created_at=datetime.now(UTC), created_by_email=actor.email,
        )
        self.prompts.append(row)
        return row

    async def prompt_version(self, agent: str, version: int) -> Any:
        return next((row for row in self.prompts if row.agent == agent and row.version == version), None)


class Args(ToolInput):
    pass


async def _noop(invocation):  # pragma: no cover - never run
    return ToolOutput(data=None, summary="")


def tool(name: str, kind: ToolKind = ToolKind.READ, scope: ToolScope = ToolScope.READ) -> ToolDefinition:
    return ToolDefinition(
        name=name, description=name, kind=kind, scope=scope, category=ToolCategory.INTELLIGENCE, input_model=Args, handler=_noop
    )


def make_runtime(settings, store: FakeStore) -> tuple[AdminRuntime, ModelRouter, ToolRegistry]:
    rules = RoutingRules(
        complex=Route("gemini", ("gemini-3.5-flash",)),
        simple=Route("openrouter", ("a:free",)),
        failover=Route("openrouter", ("b:free",)),
        web_grounded=Route("gemini", ("gemini-2.5-flash",)),
    )
    router = ModelRouter({}, rules, NoopTracingClient())
    registry = ToolRegistry([tool("web_search"), tool("search_emails"), tool("undo_actions", ToolKind.WRITE, ToolScope.COMPENSATION)])
    runtime = AdminRuntime(settings=settings, store=store, redis=None, router=router, registry=registry, budgets=None, key_prefix="t")
    return runtime, router, registry


# ----------------------------------------------------------------------------- guard
async def test_guard_lets_a_super_admin_through_and_caches_the_answer():
    auth = AuthService()
    guard = make_guard(auth)
    actor = await guard.require_super_admin(Principal(user_id=ADMIN))
    assert actor.user_id == ADMIN and actor.email == "boss@rolesync.test"
    await guard.require_super_admin(Principal(user_id=ADMIN))
    assert auth.calls == 1


async def test_guard_refuses_everyone_else_with_403():
    guard = make_guard(AuthService())
    with pytest.raises(NotSuperAdmin) as refused:
        await guard.require_super_admin(Principal(user_id=REP))
    assert refused.value.status_code == 403
    with pytest.raises(AuthenticationFailed):
        await guard.require_super_admin(None)


async def test_guard_fails_closed_when_auth_service_is_unreachable_and_does_not_cache_that():
    auth = AuthService()
    auth.down = True
    guard = make_guard(auth)
    with pytest.raises(UpstreamUnavailable) as unavailable:
        await guard.require_super_admin(Principal(user_id=ADMIN))
    assert unavailable.value.status_code == 503
    auth.down = False
    assert (await guard.require_super_admin(Principal(user_id=ADMIN))).user_id == ADMIN


async def test_guard_fails_closed_without_the_internal_token():
    auth = AuthService()
    with pytest.raises(UpstreamUnavailable):
        await make_guard(auth, token=None).require_super_admin(Principal(user_id=ADMIN))
    assert auth.calls == 0


async def test_guard_asks_again_after_the_cache_expires():
    auth = AuthService()
    now = [0.0]
    guard = make_guard(auth, now=now)
    await guard.require_super_admin(Principal(user_id=ADMIN))
    now[0] = 31.0
    await guard.require_super_admin(Principal(user_id=ADMIN))
    assert auth.calls == 2


# ----------------------------------------------------------------------------- runtime
async def test_overrides_reach_the_router_the_registry_and_the_prompts(settings):
    store = FakeStore()
    runtime, router, registry = make_runtime(settings, store)
    store.settings["routes"] = SettingRecord({"complex": {"provider": "openrouter", "models": ["x/y", "z:free"]}}, 1, None, None)
    store.settings["tools"] = SettingRecord({"disabled": ["search_emails", "undo_actions"]}, 1, None, None)
    store.settings["controls"] = SettingRecord(
        {"agent_enabled": True, "sub_agents_enabled": True, "web_search_enabled": False, "limits": {"max_steps_per_turn": 7}}, 1, None, None
    )
    await store.publish_prompt("research", mode="APPEND", instructions="Be brief.", note=None, actor=SimpleNamespace(email=None))
    await runtime.refresh()

    assert router.rules.complex == Route("openrouter", ("x/y", "z:free"))
    assert router.rules.simple == Route("openrouter", ("a:free",))  # untouched routes keep the default
    names = {d.name for d in AgentScopes().tools_for("orchestrator", registry)}
    assert names == {"undo_actions"}  # web search switched off, search_emails disabled, undo_actions protected
    assert runtime.limit("max_steps_per_turn") == 7 and runtime.limit("max_tool_calls_per_turn") == settings.max_tool_calls_per_turn
    assert runtime.prompt_body("research", "BASE").endswith("Be brief.")
    assert runtime.prompt_body("quote", "BASE") == "BASE"
    assert compose_prompt("BASE", "REPLACE", "Only this.") == "Only this."
    assert runtime.price("openrouter", "anything:free") is not None and runtime.price("openrouter", "paid/model") is None


# ----------------------------------------------------------------------------- endpoints
class FakeVerifier:
    async def verify(self, token: str) -> Principal:
        return Principal(user_id=UUID(token))


@pytest.fixture
def console(settings):
    store = FakeStore()
    runtime, router, registry = make_runtime(settings, store)
    auth = AuthService()
    app = FastAPI()
    install_error_handlers(app)
    app.include_router(admin_api.router, prefix="/api/v1/sales-agent")
    app.state.container = SimpleNamespace(
        settings=settings, token_verifier=FakeVerifier(), admin_guard=make_guard(auth), admin=runtime, router=router, registry=registry
    )
    client = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://engine.test/api/v1/sales-agent/admin")
    return SimpleNamespace(client=client, store=store, runtime=runtime, auth=auth)


def as_user(user_id: UUID) -> dict[str, str]:
    return {"Authorization": f"Bearer {user_id}"}


async def test_endpoints_need_a_signed_in_super_admin(console):
    assert (await console.client.get("/controls")).status_code == 401
    refused = await console.client.get("/controls", headers=as_user(REP))
    assert refused.status_code == 403 and refused.json()["code"] == "NOT_SUPER_ADMIN"
    console.auth.down = True
    assert (await console.client.get("/controls", headers=as_user(ADMIN))).status_code == 503


async def test_pausing_the_agent_is_saved_applied_and_audited(console):
    before = (await console.client.get("/controls", headers=as_user(ADMIN))).json()
    assert before["agent_enabled"] is True and before["version"] == 0
    assert before["limits"]["max_steps_per_turn"]["overridden"] is False

    body = {
        "agent_enabled": False,
        "maintenance_message": "Back soon",
        "sub_agents_enabled": False,
        "web_search_enabled": True,
        "limits": {"max_steps_per_turn": 12, "max_tool_calls_per_turn": None},
    }
    saved = await console.client.put("/controls", json=body, headers=as_user(ADMIN))
    assert saved.status_code == 200, saved.text
    data = saved.json()
    assert data["agent_enabled"] is False and data["maintenance_message"] == "Back soon" and data["version"] == 1
    assert data["limits"]["max_steps_per_turn"] == {
        "value": 12, "default": console.runtime.default_limit("max_steps_per_turn"), "overridden": True, "min": 1, "max": 100
    }
    assert console.runtime.agent_enabled is False and "delegate" in console.runtime.disabled_tools()
    assert console.store.audits[-1]["action"] == "agent.paused"

    out_of_range = await console.client.put("/controls", json=body | {"limits": {"max_steps_per_turn": 0}}, headers=as_user(ADMIN))
    assert out_of_range.status_code == 422


async def test_tools_can_be_switched_off_but_protected_ones_cannot(console, monkeypatch):
    async def no_stats(container):
        return {}

    monkeypatch.setattr(admin_api, "_tool_stats", no_stats)
    off = await console.client.put("/tools/search_emails", json={"enabled": False}, headers=as_user(ADMIN))
    assert off.status_code == 200 and off.json()["enabled"] is False
    assert not console.runtime._registry.is_enabled("search_emails")  # noqa: SLF001
    assert (await console.client.patch("/tools/undo_actions", json={"enabled": False}, headers=as_user(ADMIN))).status_code == 409
    assert (await console.client.put("/tools/nope", json={"enabled": False}, headers=as_user(ADMIN))).status_code == 404


async def test_prompts_publish_restore_and_preview(console):
    listed = (await console.client.get("/prompts", headers=as_user(ADMIN))).json()
    assert [item["agent"] for item in listed] == ["orchestrator", "research", "outreach", "quote"]
    assert listed[0]["active"] is None and listed[0]["base_prompt"] == BASE_PROMPT

    published = await console.client.post(
        "/prompts/orchestrator", json={"mode": "APPEND", "instructions": "Always sign off with Cheers.", "note": "tone"}, headers=as_user(ADMIN)
    )
    assert published.status_code == 200, published.text
    assert published.json()["active"]["version"] == 1
    assert console.runtime.prompt_body("orchestrator", BASE_PROMPT).endswith("Always sign off with Cheers.")

    too_short = await console.client.post("/prompts/orchestrator", json={"mode": "REPLACE", "instructions": "short"}, headers=as_user(ADMIN))
    assert too_short.status_code == 422

    await console.client.post("/prompts/orchestrator", json={"mode": "APPEND", "instructions": ""}, headers=as_user(ADMIN))
    restored = (await console.client.post("/prompts/orchestrator/versions/1/restore", headers=as_user(ADMIN))).json()
    assert restored["active"]["version"] == 3 and restored["active"]["instructions"] == "Always sign off with Cheers."
    assert [v["active"] for v in restored["versions"]] == [True, False, False]

    preview = await console.client.post(
        "/prompts/preview", json={"agent": "quote", "mode": "REPLACE", "instructions": "x" * 60}, headers=as_user(ADMIN)
    )
    assert preview.status_code == 200 and preview.json()["system_prompt"].startswith("x" * 60)
