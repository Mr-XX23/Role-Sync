"""Model router (implementation-plan §5): complexity picks the route, Gemini failure fails
over to OpenRouter. Every agent asks the router for a brain; nothing calls a provider
directly, so routing lives in one place and providers stay swappable.

For the same reason the router is where model usage is metered (credits): each attempt that used
tokens is reported to the ``UsageMeter`` exactly once, whoever made the call.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator, Mapping, Sequence
from dataclasses import dataclass
from typing import Protocol

from app.models.providers.base import LLMProvider
from app.models.types import (
    Complexity,
    Completion,
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
    """Where the router reports usage (``app.billing.metering.UsageMeter``). Must not block or raise."""

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


class ModelRouter:
    def __init__(
        self,
        providers: Mapping[str, LLMProvider],
        rules: RoutingRules,
        tracer: TracingClient,
        *,
        meter: ModelUsageMeter | None = None,
    ) -> None:
        self._providers = dict(providers)
        self._rules = rules
        self._tracer = tracer
        self._meter = meter

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
                            self._meter_usage(task, route.provider, event.completion.model, event.completion.usage)
                        yield event
                return
            except ProviderError as exc:
                if not metered and exc.usage is not None and exc.usage.output_tokens > 0:
                    # The attempt failed after the model had produced tokens: those were used all the same.
                    self._meter_usage(task, route.provider, exc.model or route.models[0], exc.usage, partial=True)
                if not has_fallback:
                    raise
                logger.warning("%s failed for %s, failing over: %s", route.provider, task.purpose, exc)
                if emitted_text:
                    yield StreamRestart(reason=f"{route.provider} failed mid-answer; retrying on {routes[position + 1].provider}")

    def _meter_usage(self, task: TaskSpec, provider: str, model: str, usage: Usage, *, partial: bool = False) -> None:
        if self._meter is None:
            return
        try:
            self._meter.model_call(task, provider=provider, model=model, usage=usage, partial=partial)
        except Exception:  # metering never fails a model call
            logger.warning("could not meter the %s call", task.purpose, exc_info=True)
