"""The Super Admin Console's overrides, applied to the running engine.

Overrides live in Postgres (``agent.admin_setting`` and ``agent.prompt_version``) so every instance
shares them; each instance re-reads them every few seconds (and at once after its own admin writes)
and applies them to the live objects: routing rules, disabled tools, per-turn limits, tenant budgets
and prompts. Stop requests for single sessions live in Redis, read at every step of the run.

A database that doesn't have the admin tables yet (migration 0007 not applied) leaves the engine
on its built-in defaults.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
from uuid import UUID

from redis.asyncio import Redis

from app.config import Settings
from app.engine.guardrails.limits import Halt, HaltReason, TurnLimits
from app.models.router import ModelRouter, Route, RoutingRules

logger = logging.getLogger(__name__)

LIMIT_BOUNDS: dict[str, tuple[int, int]] = {
    "max_steps_per_turn": (1, 100),
    "max_tool_calls_per_turn": (1, 500),
    "max_tokens_per_turn": (1_000, 10_000_000),
    "max_identical_tool_calls": (1, 20),
    "max_concurrent_runs_per_tenant": (1, 100),
    "turns_per_minute_per_user": (1, 600),
    "tokens_per_day_per_tenant": (0, 1_000_000_000),
}

ROUTES: dict[str, tuple[str, str]] = {
    "complex": ("Complex work", "Planning, tool use, negotiation and quotes: every agent and sub-agent step."),
    "simple": ("Simple tasks", "Summaries and classification, such as prospect brief digests."),
    "failover": ("Failover", "Used when the complex route fails, in the order listed."),
    "web_grounded": ("Web answers", "Google Search grounding for web search. Only Gemini can ground answers."),
}

PROVIDERS: dict[str, tuple[str, bool]] = {  # name: (label, supports an ordered model list)
    "gemini": ("Google Gemini", False),
    "openrouter": ("OpenRouter", True),
}

# USD per million tokens (docs/billing/cost-model-and-credit-system.md section 2, Sept 2026).
# OpenRouter ":free" models cost nothing whether or not they are listed.
DEFAULT_RATES: list[dict[str, Any]] = [
    {"provider": "gemini", "model": "gemini-3.5-flash", "input_per_million_usd": 1.50, "output_per_million_usd": 9.00, "request_fee_usd": 0.0},
    {"provider": "gemini", "model": "gemini-3.5-flash-lite", "input_per_million_usd": 0.30, "output_per_million_usd": 2.50, "request_fee_usd": 0.0},
    {"provider": "gemini", "model": "gemini-3.6-flash", "input_per_million_usd": 0.75, "output_per_million_usd": 3.75, "request_fee_usd": 0.0},
    {"provider": "gemini", "model": "gemini-2.5-flash", "input_per_million_usd": 0.30, "output_per_million_usd": 2.50, "request_fee_usd": 0.0},
    {"provider": "gemini", "model": "gemini-2.5-flash-lite", "input_per_million_usd": 0.10, "output_per_million_usd": 0.40, "request_fee_usd": 0.0},
]

PROTECTED_TOOLS = frozenset({"undo_actions", "read_offloaded_result"})  # safety and context: never switched off
SUB_AGENT_TOOLS = frozenset({"delegate"})
WEB_SEARCH_TOOLS = frozenset({"web_search", "research_prospect"})

PAUSED_MESSAGE = "The sales agent is paused by the RoleSync team. Try again later."
STOPPED_MESSAGE = "An administrator stopped this request. Actions that already completed stay done."
STOP_TTL_SECONDS = 86_400


@dataclass
class SettingRecord:
    value: dict[str, Any]
    version: int
    updated_at: datetime | None
    updated_by_email: str | None


@dataclass
class AdminSnapshot:
    controls: SettingRecord | None = None
    tools: SettingRecord | None = None
    routes: SettingRecord | None = None
    rates: SettingRecord | None = None
    prompts: dict[str, tuple[str, str]] = field(default_factory=dict)  # agent: (mode, instructions)


def compose_prompt(base: str, mode: str | None, instructions: str | None) -> str:
    text = (instructions or "").strip()
    if not text:
        return base
    if mode == "REPLACE":
        return text
    return f"{base}\n\nAdditional instructions from the RoleSync team:\n{text}"


def rate_key(provider: str, model: str) -> tuple[str, str]:
    return provider.strip().lower(), model.strip()


class AdminRuntime:
    def __init__(
        self,
        *,
        settings: Settings,
        store: Any,  # app.admin.store.AdminStore
        redis: Redis,
        router: ModelRouter,
        registry: Any,
        budgets: Any,
        key_prefix: str,
    ) -> None:
        self.settings = settings
        self.store = store
        self._redis = redis
        self._router = router
        self._registry = registry
        self._budgets = budgets
        self._prefix = key_prefix
        self._default_rules = router.rules
        self.orchestrator: Any = None  # set once the orchestrator exists
        self.snapshot = AdminSnapshot()

    # ------------------------------------------------------------------ refresh
    async def refresh(self) -> None:
        try:
            self.snapshot = await self.store.load_snapshot()
        except Exception as exc:
            logger.warning("could not load admin overrides (keeping the current ones): %s", exc)
            return
        self.apply()

    async def run_forever(self) -> None:
        while True:
            await self.refresh()
            await asyncio.sleep(max(1.0, self.settings.admin_refresh_seconds))

    def apply(self) -> None:
        self._router.set_rules(self.rules())
        self._registry.set_disabled(self.disabled_tools())
        if self._budgets is not None:
            self._budgets.configure(
                turns_per_minute_per_user=self.limit("turns_per_minute_per_user"),
                tokens_per_day_per_tenant=self.limit("tokens_per_day_per_tenant"),
            )
        if self.orchestrator is not None:
            self.orchestrator.set_limits(
                TurnLimits(
                    max_steps=self.limit("max_steps_per_turn"),
                    max_tool_calls=self.limit("max_tool_calls_per_turn"),
                    max_tokens=self.limit("max_tokens_per_turn"),
                    max_identical_calls=self.limit("max_identical_tool_calls"),
                )
            )

    # ------------------------------------------------------------------ controls
    def _controls(self) -> dict[str, Any]:
        return self.snapshot.controls.value if self.snapshot.controls else {}

    @property
    def agent_enabled(self) -> bool:
        return bool(self._controls().get("agent_enabled", True))

    @property
    def maintenance_message(self) -> str | None:
        return self._controls().get("maintenance_message") or None

    @property
    def sub_agents_enabled(self) -> bool:
        return bool(self._controls().get("sub_agents_enabled", True))

    @property
    def web_search_enabled(self) -> bool:
        return bool(self._controls().get("web_search_enabled", True))

    def default_limit(self, key: str) -> int:
        return int(getattr(self.settings, key))

    def limit_override(self, key: str) -> int | None:
        value = (self._controls().get("limits") or {}).get(key)
        return int(value) if isinstance(value, int) and not isinstance(value, bool) else None

    def limit(self, key: str) -> int:
        override = self.limit_override(key)
        return self.default_limit(key) if override is None else override

    # ------------------------------------------------------------------ tools
    def explicitly_disabled(self) -> frozenset[str]:
        value = self.snapshot.tools.value if self.snapshot.tools else {}
        return frozenset(value.get("disabled") or ()) - PROTECTED_TOOLS

    def disabled_tools(self) -> frozenset[str]:
        disabled = set(self.explicitly_disabled())
        if not self.sub_agents_enabled:
            disabled |= SUB_AGENT_TOOLS
        if not self.web_search_enabled:
            disabled |= WEB_SEARCH_TOOLS
        return frozenset(disabled)

    # ------------------------------------------------------------------ routes
    def default_route(self, name: str) -> Route | None:
        return getattr(self._default_rules, name)

    def route_override(self, name: str) -> Route | None:
        value = (self.snapshot.routes.value if self.snapshot.routes else {}).get(name)
        if not isinstance(value, dict) or not value.get("provider") or not value.get("models"):
            return None
        return Route(str(value["provider"]), tuple(str(m) for m in value["models"]))

    def route(self, name: str) -> Route | None:
        return self.route_override(name) or self.default_route(name)

    def rules(self) -> RoutingRules:
        return RoutingRules(
            complex=self.route("complex"),  # type: ignore[arg-type]
            simple=self.route("simple"),  # type: ignore[arg-type]
            failover=self.route("failover"),  # type: ignore[arg-type]
            web_grounded=self.route("web_grounded"),
        )

    # ------------------------------------------------------------------ rates
    def custom_rates(self) -> list[dict[str, Any]]:
        value = self.snapshot.rates.value if self.snapshot.rates else {}
        return list(value.get("rates") or [])

    def rates(self) -> list[dict[str, Any]]:
        merged: dict[tuple[str, str], dict[str, Any]] = {}
        for rate in DEFAULT_RATES:
            merged[rate_key(rate["provider"], rate["model"])] = {**rate, "source": "default"}
        for rate in self.custom_rates():
            merged[rate_key(rate["provider"], rate["model"])] = {**rate, "source": "custom"}
        return list(merged.values())

    def price(self, provider: str, model: str) -> dict[str, Any] | None:
        """The rate for a model, if it has one (OpenRouter ``:free`` models are free)."""
        table = {rate_key(rate["provider"], rate["model"]): rate for rate in self.rates()}
        rate = table.get(rate_key(provider, model))
        if rate is None and provider == "openrouter" and model.endswith(":free"):
            return {"input_per_million_usd": 0.0, "output_per_million_usd": 0.0, "request_fee_usd": 0.0}
        return rate

    # ------------------------------------------------------------------ prompts
    def prompt_body(self, agent: str, base: str) -> str:
        mode, instructions = self.snapshot.prompts.get(agent, (None, None))
        return compose_prompt(base, mode, instructions)

    # ------------------------------------------------------------------ pause + stop
    def _stop_key(self, session_id: UUID) -> str:
        return f"{self._prefix}:admin:stop:{session_id}"

    async def request_stop(self, session_id: UUID) -> None:
        await self._redis.set(self._stop_key(session_id), "1", ex=STOP_TTL_SECONDS)

    async def clear_stop(self, session_id: UUID) -> None:
        await self._redis.delete(self._stop_key(session_id))

    async def stop_requested(self, session_ids: list[UUID]) -> set[UUID]:
        if not session_ids:
            return set()
        values = await self._redis.mget([self._stop_key(sid) for sid in session_ids])
        return {sid for sid, value in zip(session_ids, values, strict=True) if value}

    async def halt_for(self, session_id: UUID, *, consume: bool, include_pause: bool = True) -> Halt | None:
        """Why this run must stop now, if it must: an administrator's stop, or the agent paused platform-wide."""
        key = self._stop_key(session_id)
        if await self._redis.exists(key):
            if consume:
                await self._redis.delete(key)
            return Halt(HaltReason.ADMIN_STOP, STOPPED_MESSAGE)
        if include_pause and not self.agent_enabled:
            return Halt(HaltReason.PAUSED, self.maintenance_message or PAUSED_MESSAGE)
        return None
