"""Model router (implementation-plan §5): complexity picks the route, Gemini failure fails
over to OpenRouter. Every agent asks the router for a brain; nothing calls a provider
directly, so routing lives in one place and providers stay swappable.

For the same reason the router is where model usage is reported, twice over: the Super Admin
Console's usage stats (``meter``) and credits (``credit_meter``), where each attempt that used
tokens is charged exactly once, whoever made the call.
"""

from __future__ import annotations

import logging
import time
from collections.abc import AsyncIterator, Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Protocol

from app.models.providers.base import LLMProvider
from app.models.types import (
    Complexity,
    Completion,
    Message,
    Role,
    ProviderError,
    ProviderUnavailable,
    StreamDone,
    StreamEvent,
    StreamRestart,
    TaskSpec,
    TextDelta,
    Usage,
)
from app.observability.tracing import TracingClient

logger = logging.getLogger(__name__)


class ModelUsageMeter(Protocol):
    """Where the router reports usage for credits (``app.billing.metering.UsageMeter``). Must not block or raise."""

    def model_call(self, task: TaskSpec, *, provider: str, model: str, usage: Usage, partial: bool = False) -> None: ...


@dataclass(frozen=True, slots=True)
class Route:
    provider: str
    models: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class RoutingRules:
    complex: Route  # Gemini
    simple: Route  # OpenRouter
    failover: Route  # OpenRouter, used when the complex route fails
    web_grounded: Route | None = None  # Gemini with Google Search; no failover (nothing else can ground)

    def routes_for(self, task: TaskSpec) -> Sequence[Route]:
        if task.web_grounded:
            return (self.web_grounded,) if self.web_grounded else ()
        if task.complexity is Complexity.HIGH:
            return (self.complex, self.failover)
        return (self.simple,)


# Records a finished model call (usage metering). Best-effort: it must never fail the call.
UsageMeter = Callable[[TaskSpec, Completion, int], Awaitable[None]]


class ModelRouter:
    def __init__(
        self,
        providers: Mapping[str, LLMProvider],
        rules: RoutingRules,
        tracer: TracingClient,
        meter: UsageMeter | None = None,
        *,
        credit_meter: ModelUsageMeter | None = None,
    ) -> None:
        self._providers = dict(providers)
        self._rules = rules
        self._tracer = tracer
        self._meter = meter
        self._credit_meter = credit_meter

    @property
    def rules(self) -> RoutingRules:
        return self._rules

    def set_rules(self, rules: RoutingRules) -> None:
        """Swap the routing rules (the Super Admin Console's route overrides); the next call uses them."""
        self._rules = rules

    def set_meter(self, meter: UsageMeter | None) -> None:
        self._meter = meter

    def configured_providers(self) -> frozenset[str]:
        return frozenset(self._providers)

    async def test_model(self, provider: str, model: str, prompt: str, *, max_output_tokens: int = 32) -> Completion:
        """One short call to exactly this provider and model, bypassing the routes (admin model test).

        Not charged in credits: it belongs to no workspace."""
        if provider not in self._providers:
            raise ProviderUnavailable(f"provider '{provider}' is not configured")
        task = TaskSpec(
            purpose="admin:model-test",
            messages=(Message(role=Role.USER, content=prompt),),
            complexity=Complexity.LOW,
            max_output_tokens=max_output_tokens,
        )
        started = time.monotonic()
        async for event in self._providers[provider].stream(task, (model,)):
            if isinstance(event, StreamDone):
                await self._record(task, event.completion, started)
                return event.completion
        raise ProviderError("model stream ended without a completion")

    async def _record(self, task: TaskSpec, completion: Completion, started: float) -> None:
        if self._meter is None:
            return
        try:
            await self._meter(task, completion, int((time.monotonic() - started) * 1000))
        except Exception:
            logger.warning("could not record model usage for %s", task.purpose, exc_info=True)

    def can_serve(self, task: TaskSpec) -> bool:
        """Whether any configured provider could take this kind of task."""
        return any(route.provider in self._providers for route in self._rules.routes_for(task))

    async def complete(self, task: TaskSpec) -> Completion:
        async for event in self.stream(task):
            if isinstance(event, StreamDone):
                return event.completion
        raise ProviderError("model stream ended without a completion")

    async def stream(self, task: TaskSpec) -> AsyncIterator[StreamEvent]:
        routes = [route for route in self._rules.routes_for(task) if route.provider in self._providers]
        if not routes:
            kind = "web-grounded" if task.web_grounded else f"{task.complexity.value}-complexity"
            raise ProviderUnavailable(f"no configured provider for {kind} tasks")

        for position, route in enumerate(routes):
            has_fallback = position + 1 < len(routes)
            emitted_text = False
            started = time.monotonic()
            metered = False
            try:
                async with self._tracer.span(
                    f"llm:{task.purpose}",
                    kind="llm",
                    inputs={"messages": [m.to_dict() for m in task.messages], "system": task.system},
                    metadata={
                        "provider": route.provider,
                        "models": list(route.models),
                        "complexity": task.complexity.value,
                        "web_grounded": task.web_grounded,
                    },
                ) as span:
                    async for event in self._providers[route.provider].stream(task, route.models):
                        if isinstance(event, TextDelta):
                            emitted_text = True
                        elif isinstance(event, StreamDone):
                            span.set_outputs(
                                {
                                    "message": event.completion.message.to_dict(),
                                    "model": event.completion.model,
                                    "usage": {
                                        "input_tokens": event.completion.usage.input_tokens,
                                        "output_tokens": event.completion.usage.output_tokens,
                                    },
                                }
                            )
                            # Before the completion is handed on: consumers stop reading at StreamDone.
                            metered = True
                            self._charge_credits(task, route.provider, event.completion.model, event.completion.usage)
                            await self._record(task, event.completion, started)
                        yield event
                return
            except ProviderError as exc:
                if not metered and exc.usage is not None and exc.usage.output_tokens > 0:
                    # The attempt failed after the model had produced tokens: those were used all the same.
                    self._charge_credits(task, route.provider, exc.model or route.models[0], exc.usage, partial=True)
                if not has_fallback:
                    raise
                logger.warning("%s failed for %s, failing over: %s", route.provider, task.purpose, exc)
                if emitted_text:
                    yield StreamRestart(reason=f"{route.provider} failed mid-answer; retrying on {routes[position + 1].provider}")

    def _charge_credits(self, task: TaskSpec, provider: str, model: str, usage: Usage, *, partial: bool = False) -> None:
        if self._credit_meter is None:
            return
        try:
            self._credit_meter.model_call(task, provider=provider, model=model, usage=usage, partial=partial)
        except Exception:  # metering never fails a model call
            logger.warning("could not meter the %s call", task.purpose, exc_info=True)
