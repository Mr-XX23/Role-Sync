"""Collects the provider usage a unit of work spends, so it can be charged once when the work ends.

The code that calls a provider records what the call cost (``record_tokens``,
``record_llamaparse_pages``, ``record_composio_execution``) without knowing who pays for it. Whoever
owns the work - an ingestion stage, a search request, a sync run - opens a scope around it, and
charges what the scope collected. Recording outside any scope does nothing.

Scopes live in context variables, so they follow the work across ``await`` and into
``asyncio.to_thread`` (which copies the context); concurrent documents each have their own. There
are two independent scopes: usage (tokens and LlamaParse pages, charged per document or request)
and connector executions (Composio calls, charged per sync run), because a sync run processes many
documents that are each charged on their own.
"""
from __future__ import annotations

import contextvars
import threading
from contextlib import contextmanager
from typing import Any, Iterator, Optional

UNIT_LLAMAPARSE_PAGE = "LLAMAPARSE_PAGE"
UNIT_COMPOSIO_EXECUTION = "COMPOSIO_EXECUTION"

# billing-service accepts at most this many items per usage report.
MAX_ITEMS = 50

# Gemini's batchEmbedContents returns no token counts, so embedding tokens are estimated from the
# characters sent, with the same ratio the sales-agent-engine uses for its context budget
# (app/context/manager.py CHARS_PER_TOKEN = 3.5).
CHARS_PER_TOKEN = 3.5


def estimate_tokens(chars: int) -> int:
    """Tokens in ``chars`` characters of text, estimated at 3.5 characters per token."""
    chars = int(chars or 0)
    return int(chars / CHARS_PER_TOKEN) + 1 if chars > 0 else 0


class UsageMeter:
    """Tokens per model and counted units, plus a per-purpose breakdown for the report's metadata."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._tokens: dict[str, list[int]] = {}  # model -> [input, cached input, output]
        self._units: dict[str, float] = {}
        self._purposes: dict[str, dict[str, Any]] = {}

    # ---- recording ---------------------------------------------------------
    def add_tokens(
        self,
        model: str,
        input_tokens: int = 0,
        output_tokens: int = 0,
        cached_input_tokens: int = 0,
        *,
        purpose: str = "",
        estimated: bool = False,
    ) -> None:
        model = str(model or "").strip() or "unknown"
        inputs = max(0, int(input_tokens or 0))
        outputs = max(0, int(output_tokens or 0))
        cached = min(inputs, max(0, int(cached_input_tokens or 0)))
        if inputs == 0 and outputs == 0:
            return
        with self._lock:
            totals = self._tokens.setdefault(model, [0, 0, 0])
            totals[0] += inputs
            totals[1] += cached
            totals[2] += outputs
            if purpose:
                entry = self._purposes.setdefault(purpose, {"calls": 0, "inputTokens": 0, "outputTokens": 0})
                entry["calls"] = int(entry.get("calls", 0)) + 1
                entry["inputTokens"] = int(entry.get("inputTokens", 0)) + inputs
                entry["outputTokens"] = int(entry.get("outputTokens", 0)) + outputs
                models = entry.setdefault("models", [])
                if model not in models:
                    models.append(model)
                if estimated:
                    entry["estimated"] = True

    def add_units(self, unit: str, quantity: float, *, purpose: str = "") -> None:
        try:
            amount = float(quantity or 0)
        except (TypeError, ValueError):
            return
        if amount <= 0 or not unit:
            return
        with self._lock:
            self._units[unit] = self._units.get(unit, 0.0) + amount
            if purpose:
                entry = self._purposes.setdefault(purpose, {})
                entry[unit] = _number(float(entry.get(unit, 0)) + amount)

    def merge(self, other: "UsageMeter | dict[str, Any] | None") -> "UsageMeter":
        """Add another meter's usage (or its ``to_dict`` form) to this one."""
        if other is None:
            return self
        data = other.to_dict() if isinstance(other, UsageMeter) else other
        if not isinstance(data, dict):
            return self
        with self._lock:
            for model, values in (data.get("tokens") or {}).items():
                try:
                    inputs, cached, outputs = (max(0, int(v or 0)) for v in list(values)[:3])
                except (TypeError, ValueError):
                    continue
                totals = self._tokens.setdefault(str(model), [0, 0, 0])
                totals[0] += inputs
                totals[1] += min(cached, inputs)
                totals[2] += outputs
            for unit, amount in (data.get("units") or {}).items():
                try:
                    value = float(amount or 0)
                except (TypeError, ValueError):
                    continue
                if value > 0:
                    self._units[str(unit)] = self._units.get(str(unit), 0.0) + value
            for purpose, entry in (data.get("purposes") or {}).items():
                if not isinstance(entry, dict):
                    continue
                mine = self._purposes.setdefault(str(purpose), {})
                for field, value in entry.items():
                    if field == "models" and isinstance(value, list):
                        models = mine.setdefault("models", [])
                        models.extend(m for m in value if m not in models)
                    elif field == "estimated":
                        mine["estimated"] = bool(mine.get("estimated") or value)
                    elif isinstance(value, (int, float)):
                        mine[field] = _number(float(mine.get(field, 0) or 0) + float(value))
        return self

    # ---- reading -----------------------------------------------------------
    def is_empty(self) -> bool:
        with self._lock:
            return not self._tokens and not self._units

    def units(self, unit: str) -> float:
        with self._lock:
            return self._units.get(unit, 0.0)

    def tokens(self, model: str) -> tuple[int, int, int]:
        """(input, cached input, output) recorded for ``model``."""
        with self._lock:
            values = self._tokens.get(model) or [0, 0, 0]
            return values[0], values[1], values[2]

    def items(self) -> list[dict[str, Any]]:
        """Usage report items in the contract's shape: TOKENS per model, then UNITS."""
        with self._lock:
            items: list[dict[str, Any]] = [
                {
                    "type": "TOKENS",
                    "model": model,
                    "inputTokens": values[0],
                    "cachedInputTokens": values[1],
                    "outputTokens": values[2],
                }
                for model, values in sorted(self._tokens.items())
            ]
            items.extend(
                {"type": "UNITS", "unit": unit, "quantity": _number(amount)}
                for unit, amount in sorted(self._units.items())
            )
        return items[:MAX_ITEMS]

    def purposes(self) -> dict[str, Any]:
        with self._lock:
            return {name: dict(entry) for name, entry in self._purposes.items()}

    def to_dict(self) -> dict[str, Any]:
        """JSON-safe form, carried in queue payloads from one ingestion stage to the next."""
        with self._lock:
            return {
                "tokens": {model: list(values) for model, values in self._tokens.items()},
                "units": {unit: _number(amount) for unit, amount in self._units.items()},
                "purposes": {name: dict(entry) for name, entry in self._purposes.items()},
            }

    @classmethod
    def from_dict(cls, data: Any) -> "UsageMeter":
        return cls().merge(data if isinstance(data, dict) else None)


def _number(value: float) -> float | int:
    return int(value) if float(value).is_integer() else round(float(value), 6)


# ---- scopes -----------------------------------------------------------------
_usage_meter: contextvars.ContextVar[Optional[UsageMeter]] = contextvars.ContextVar("billing_usage_meter", default=None)
_execution_meter: contextvars.ContextVar[Optional[UsageMeter]] = contextvars.ContextVar(
    "billing_execution_meter", default=None
)


@contextmanager
def _scope(var: contextvars.ContextVar, meter: Optional[UsageMeter], join: bool) -> Iterator[UsageMeter]:
    current = var.get()
    if join and meter is None and current is not None:
        yield current
        return
    active = meter if meter is not None else UsageMeter()
    token = var.set(active)
    try:
        yield active
    finally:
        try:
            var.reset(token)
        except ValueError:  # exited in another context; restore what was there before
            var.set(current)


def usage_scope(meter: Optional[UsageMeter] = None, *, join: bool = False):
    """Collect tokens and LlamaParse pages recorded inside the block.

    ``meter``: collect into this meter (to continue one started earlier). ``join``: when a usage
    scope is already open, add to it instead of starting a separate one.
    """
    return _scope(_usage_meter, meter, join)


def execution_scope(meter: Optional[UsageMeter] = None):
    """Collect the Composio executions made inside the block (a sync run, a webhook, a sweep)."""
    return _scope(_execution_meter, meter, False)


def current_usage() -> Optional[UsageMeter]:
    return _usage_meter.get()


# ---- recording helpers (no-ops outside a scope; never raise) -------------------
def record_tokens(
    model: str,
    input_tokens: int,
    output_tokens: int = 0,
    cached_input_tokens: int = 0,
    *,
    purpose: str = "",
    estimated: bool = False,
) -> None:
    try:
        meter = _usage_meter.get()
        if meter is not None:
            meter.add_tokens(model, input_tokens, output_tokens, cached_input_tokens, purpose=purpose, estimated=estimated)
    except Exception as err:  # pragma: no cover - defensive
        print(f"[Billing] Could not record tokens: {err}")


def record_units(unit: str, quantity: float, *, purpose: str = "") -> None:
    try:
        meter = _usage_meter.get()
        if meter is not None:
            meter.add_units(unit, quantity, purpose=purpose)
    except Exception as err:  # pragma: no cover - defensive
        print(f"[Billing] Could not record units: {err}")


def record_llamaparse_pages(pages: int) -> None:
    """Pages LlamaParse parsed (it bills per page). Never call this for locally parsed files."""
    record_units(UNIT_LLAMAPARSE_PAGE, pages, purpose="llamaparse")


def record_composio_execution(count: int = 1) -> None:
    """One Composio tool call (``tools.execute`` or ``tools.proxy``), made by a sync run."""
    try:
        meter = _execution_meter.get()
        if meter is not None:
            meter.add_units(UNIT_COMPOSIO_EXECUTION, count)
    except Exception as err:  # pragma: no cover - defensive
        print(f"[Billing] Could not record a Composio execution: {err}")


def record_gemini_usage(model: str, body: Any, *, purpose: str, prompt_chars: int = 0, output_chars: int = 0) -> None:
    """Tokens from a Gemini ``generateContent`` response's ``usageMetadata``.

    ``outputTokens`` includes thinking tokens (``thoughtsTokenCount``), which Gemini bills as output.
    Without usage metadata the call is estimated from the characters sent and received.
    """
    try:
        usage = body.get("usageMetadata") if isinstance(body, dict) else None
        if isinstance(usage, dict) and any(
            field in usage for field in ("promptTokenCount", "candidatesTokenCount", "thoughtsTokenCount")
        ):
            record_tokens(
                model,
                int(usage.get("promptTokenCount") or 0),
                int(usage.get("candidatesTokenCount") or 0) + int(usage.get("thoughtsTokenCount") or 0),
                int(usage.get("cachedContentTokenCount") or 0),
                purpose=purpose,
            )
        elif prompt_chars or output_chars:
            record_tokens(model, estimate_tokens(prompt_chars), estimate_tokens(output_chars), purpose=purpose, estimated=True)
    except Exception as err:  # pragma: no cover - defensive
        print(f"[Billing] Could not read Gemini usage: {err}")


def record_openrouter_usage(body: Any, requested_model: str, *, purpose: str, prompt_chars: int = 0) -> None:
    """Tokens from an OpenRouter chat completion, against the model that actually served it.

    ``completion_tokens`` already includes reasoning tokens. Without a ``usage`` block the call is
    estimated from the characters sent and received.
    """
    try:
        if not isinstance(body, dict):
            return
        model = str(body.get("model") or requested_model or "unknown")
        usage = body.get("usage")
        if isinstance(usage, dict) and ("prompt_tokens" in usage or "completion_tokens" in usage):
            details = usage.get("prompt_tokens_details") if isinstance(usage.get("prompt_tokens_details"), dict) else {}
            record_tokens(
                model,
                int(usage.get("prompt_tokens") or 0),
                int(usage.get("completion_tokens") or 0),
                int(details.get("cached_tokens") or 0),
                purpose=purpose,
            )
            return
        output_chars = 0
        for choice in body.get("choices") or []:
            message = choice.get("message") if isinstance(choice, dict) else None
            if isinstance(message, dict):
                output_chars += len(str(message.get("content") or ""))
        if prompt_chars or output_chars:
            record_tokens(model, estimate_tokens(prompt_chars), estimate_tokens(output_chars), purpose=purpose, estimated=True)
    except Exception as err:  # pragma: no cover - defensive
        print(f"[Billing] Could not read OpenRouter usage: {err}")


def count_llamaparse_pages(parser: Any, documents: Any) -> int:
    """How many pages LlamaParse returned for one ``load_data`` call.

    With ``split_by_page`` (the SDK's default, and how this service builds the client) the SDK returns
    one Document per page - it splits the job's result on the page separator - so the count of
    documents is the page count, blank pages included. Otherwise each document holds several pages
    joined by the separator.
    """
    docs = [doc for doc in (documents or []) if doc is not None]
    if not docs:
        return 0
    if getattr(parser, "split_by_page", True):
        return len(docs)
    separator = getattr(parser, "page_separator", None) or "\n---\n"
    return sum(str(getattr(doc, "text", "") or "").count(separator) + 1 for doc in docs)
