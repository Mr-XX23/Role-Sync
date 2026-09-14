"""billing-service client (``docs/billing/credit-system-api.md``: "Internal" and "Python client rules").

- ``check``: may a workspace start a paid operation now? Allowed answers are cached per workspace for a few
  seconds, so a burst of requests asks billing once, and forgotten as soon as a charge reports the balance at
  or below zero (or the account suspended). A refusal is never cached, so credits bought a moment ago count at
  once. Billing unreachable or erroring: allowed (fail open), with a warning; that answer is cached the same
  way, so an outage costs one timeout per workspace per few seconds rather than one per request.
- ``charge``: report what an operation used, after the work, under an idempotency key. When billing can't
  take it now, it goes to the Redis list ``billing:pending_usage`` and ``drain_pending`` sends it again under
  the same key, so it is never charged twice; an item is given up only after ``max_attempts`` tries. A
  request billing rejects as malformed (400, 422, ...) is logged with its body and dropped.
- ``submit``: ``charge`` in the background, for callers that must not wait (an answer streaming to the rep).
- ``BILLING_ENABLED=false``: every check is allowed and nothing is charged.

The pending list is shared with data-pipeline's billing client (same Redis, same key), and each service's
retrier sends the other's items, so both keep the same entry format and order: an entry is
``{"payload": <usage request body>, "attempts": n, "lastError": "...", "queuedAt": <epoch seconds>}``,
new entries go in at the head (LPUSH) and the retrier takes the oldest from the tail (RPOP).

Nothing here raises into the caller: a billing failure never breaks the rep's operation.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from enum import Enum
from typing import Any
from uuid import UUID, uuid4

import httpx
from redis.asyncio import Redis

logger = logging.getLogger(__name__)

PENDING_USAGE_KEY = "billing:pending_usage"

OUT_OF_CREDITS = "OUT_OF_CREDITS"
CREDITS_SUSPENDED = "CREDITS_SUSPENDED"
_REFUSAL_MESSAGES = {
    OUT_OF_CREDITS: "Your workspace is out of credits. Buy more credits to keep using the assistant.",
    CREDITS_SUSPENDED: "Credits for this workspace are suspended. Contact support.",
}

# Worth sending again later, besides 5xx: billing is busy (408, 425, 429), the same key is being charged at
# this moment (409: the resend comes back as a duplicate), or a deploy or configuration problem ops can fix
# within the retry window (401/403: the internal token; 404: the route not deployed yet). Any other 4xx
# means the request itself is wrong and would fail the same way again.
_RETRY_STATUSES = frozenset({401, 403, 404, 408, 409, 425, 429})


def new_idempotency_key() -> str:
    return f"sales-agent-engine:{uuid4()}"


@dataclass(frozen=True, slots=True)
class CreditCheck:
    allowed: bool
    code: str = "OK"  # OK | OUT_OF_CREDITS | CREDITS_SUSPENDED
    balance: float | None = None
    status: str | None = None  # ACTIVE | SUSPENDED
    verified: bool = True  # False: billing gave no usable answer (or is disabled) and the check failed open

    @property
    def message(self) -> str:
        """What to tell the rep when the operation is refused."""
        return _REFUSAL_MESSAGES.get(self.code, _REFUSAL_MESSAGES[OUT_OF_CREDITS])


_UNVERIFIED_ALLOW = CreditCheck(allowed=True, verified=False)


@dataclass(frozen=True, slots=True)
class TokensItem:
    model: str
    input_tokens: int  # the whole prompt, cached tokens included
    cached_input_tokens: int = 0
    output_tokens: int = 0  # thinking included

    def to_json(self) -> dict[str, Any]:
        return {
            "type": "TOKENS",
            "model": self.model,
            "inputTokens": self.input_tokens,
            "cachedInputTokens": self.cached_input_tokens,
            "outputTokens": self.output_tokens,
        }


@dataclass(frozen=True, slots=True)
class UnitsItem:
    unit: str  # TAVILY_SEARCH, GROUNDED_PROMPT_25, GROUNDED_PROMPT_3X, COMPOSIO_EXECUTION, ...
    quantity: int = 1

    def to_json(self) -> dict[str, Any]:
        return {"type": "UNITS", "unit": self.unit, "quantity": self.quantity}


@dataclass(frozen=True, slots=True)
class UsageCharge:
    """One ``POST /internal/v1/billing/usage``."""

    workspace_id: UUID
    user_id: UUID | None
    operation: str
    category: str
    items: tuple[TokensItem | UnitsItem, ...]
    reference: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)
    idempotency_key: str = field(default_factory=new_idempotency_key)

    def to_json(self) -> dict[str, Any]:
        return {
            "workspaceId": str(self.workspace_id),
            "userId": str(self.user_id) if self.user_id is not None else None,
            "operation": self.operation,
            "category": self.category,
            "idempotencyKey": self.idempotency_key,
            "reference": self.reference,
            "items": [item.to_json() for item in self.items],
            "metadata": dict(self.metadata),
        }


@dataclass
class DrainResult:
    sent: int = 0  # charged (or already charged under the same key)
    retrying: int = 0  # back in the queue for the next pass
    dropped: int = 0  # refused as malformed, unreadable, or out of attempts


class _Delivery(Enum):
    ACCEPTED = "accepted"
    REFUSED = "refused"  # billing rejected the request itself
    RETRY = "retry"  # billing answered but couldn't take it now
    UNREACHABLE = "unreachable"  # no answer


class BillingClient:
    def __init__(
        self,
        *,
        base_url: str,
        token: str | None,
        http: httpx.AsyncClient,
        redis: Redis | None,
        enabled: bool = True,
        timeout_seconds: float = 3.0,
        check_cache_seconds: float = 5.0,
        drain_interval_seconds: float = 30.0,
        max_attempts: int = 720,  # at the 30 s interval, about six hours of billing-service trouble
        pending_max: int = 100_000,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.enabled = enabled
        self._base_url = base_url.rstrip("/")
        self._token = token or ""
        self._http = http
        self._redis = redis
        self._timeout = httpx.Timeout(timeout_seconds)
        self._cache_seconds = check_cache_seconds
        self._drain_interval = drain_interval_seconds
        self._max_attempts = max(1, max_attempts)
        self._pending_max = pending_max
        self._clock = clock
        self._allowed: dict[UUID, tuple[float, CreditCheck]] = {}
        self._inflight: set[asyncio.Task[None]] = set()
        if enabled and not self._token:
            logger.warning("billing is enabled but INTERNAL_SERVICE_TOKEN is not set: billing-service will refuse this service")

    # ------------------------------------------------------------------ check
    async def check(self, workspace_id: UUID, user_id: UUID | None = None) -> CreditCheck:
        """Whether the workspace may start a paid operation. Fails open; never raises."""
        if not self.enabled:
            return _UNVERIFIED_ALLOW
        now = self._clock()
        cached = self._allowed.get(workspace_id)
        if cached is not None and now - cached[0] < self._cache_seconds:
            return cached[1]
        try:
            response = await self._http.get(
                f"{self._base_url}/internal/v1/billing/credits/{workspace_id}/check",
                params={"userId": str(user_id)} if user_id is not None else None,
                headers=self._headers(),
                timeout=self._timeout,
            )
        except Exception as exc:  # unreachable, timed out, anything: billing never blocks the rep
            logger.warning("credit check for workspace %s failed open: billing-service unreachable (%s)", workspace_id, type(exc).__name__)
            return self._remember(workspace_id, now, _UNVERIFIED_ALLOW)
        result = _read_check(response)
        if result is None:
            logger.warning(
                "credit check for workspace %s failed open: billing-service gave no usable answer (HTTP %s)",
                workspace_id,
                response.status_code,
            )
            result = _UNVERIFIED_ALLOW
        return self._remember(workspace_id, now, result)

    def _remember(self, workspace_id: UUID, now: float, result: CreditCheck) -> CreditCheck:
        if not result.allowed:
            self._allowed.pop(workspace_id, None)
            return result
        if len(self._allowed) >= 10_000:
            self._allowed = {key: entry for key, entry in self._allowed.items() if now - entry[0] < self._cache_seconds}
        self._allowed[workspace_id] = (now, result)
        return result

    def _note_balance(self, payload: dict[str, Any], response: httpx.Response) -> None:
        """A charge that left the workspace at or below zero, or found it suspended, ends its cached allowed
        answer: the next check asks billing instead of starting more work on a stale answer."""
        try:
            body = response.json()
            workspace_id = UUID(str(payload["workspaceId"]))
        except (ValueError, KeyError, TypeError):
            return
        if not isinstance(body, dict):
            return
        balance = body.get("balance")
        spent = isinstance(balance, int | float) and not isinstance(balance, bool) and balance <= 0
        if spent or body.get("status") == "SUSPENDED":
            self._allowed.pop(workspace_id, None)

    # ------------------------------------------------------------------ charge
    async def charge(self, usage: UsageCharge) -> None:
        """Report usage; if billing can't take it now, queue it for the background retry. Never raises."""
        if not self.enabled:
            return
        payload = usage.to_json()
        try:
            delivery, detail = await self._deliver(payload)
        except asyncio.CancelledError:
            await self._queue(payload, "stopped before billing-service answered")  # shutdown: the retry sends it
            raise
        if delivery is _Delivery.RETRY or delivery is _Delivery.UNREACHABLE:
            await self._queue(payload, detail)

    def submit(self, usage: UsageCharge) -> None:
        """``charge`` in the background: the caller carries on at once."""
        if not self.enabled:
            return
        try:
            task = asyncio.get_running_loop().create_task(self.charge(usage), name=f"billing:{usage.operation}")
        except RuntimeError:
            logger.error("no event loop to charge usage %s; it is lost: %s", usage.idempotency_key, json.dumps(usage.to_json()))
            return
        self._inflight.add(task)
        task.add_done_callback(self._settled)

    def _settled(self, task: asyncio.Task[None]) -> None:
        self._inflight.discard(task)
        if not task.cancelled() and task.exception() is not None:
            logger.error("charging usage failed unexpectedly", exc_info=task.exception())

    async def flush(self) -> None:
        """Wait for the charges ``submit`` started."""
        while pending := [task for task in self._inflight if not task.done()]:
            await asyncio.gather(*pending, return_exceptions=True)

    async def aclose(self, *, grace_seconds: float = 5.0) -> None:
        """Let charges on their way finish; ones that can't in time queue themselves for the next process."""
        pending = [task for task in self._inflight if not task.done()]
        if not pending:
            return
        _, unfinished = await asyncio.wait(pending, timeout=grace_seconds)
        for task in unfinished:
            task.cancel()
        await asyncio.gather(*unfinished, return_exceptions=True)

    async def _deliver(self, payload: dict[str, Any]) -> tuple[_Delivery, str]:
        key = payload.get("idempotencyKey")
        try:
            response = await self._http.post(
                f"{self._base_url}/internal/v1/billing/usage", json=payload, headers=self._headers(), timeout=self._timeout
            )
        except Exception as exc:
            logger.warning("billing-service unreachable for usage %s (%s)", key, type(exc).__name__)
            return _Delivery.UNREACHABLE, type(exc).__name__
        status = response.status_code
        if 200 <= status < 300:
            self._note_balance(payload, response)
            return _Delivery.ACCEPTED, ""
        detail = f"HTTP {status} {response.text[:200]}".strip()
        if status >= 500 or status in _RETRY_STATUSES:
            logger.warning("billing-service answered %s for usage %s; it will be sent again", status, key)
            return _Delivery.RETRY, detail
        logger.error("billing-service refused usage %s (%s); dropping it: %s", key, detail, json.dumps(payload))
        return _Delivery.REFUSED, detail

    async def _queue(self, payload: dict[str, Any], error: str) -> None:
        key = payload.get("idempotencyKey")
        entry = json.dumps({"payload": payload, "attempts": 1, "lastError": error[:300], "queuedAt": time.time()})
        if self._redis is not None:
            try:
                if int(await self._redis.llen(PENDING_USAGE_KEY)) >= self._pending_max:
                    logger.error("the pending usage queue is full (%d); usage %s is lost: %s", self._pending_max, key, json.dumps(payload))
                    return
                await self._redis.lpush(PENDING_USAGE_KEY, entry)  # newest at the head; the retrier takes the tail
                return
            except Exception:
                logger.warning("could not queue usage %s for a retry", key, exc_info=True)
        logger.error("usage %s could not be delivered or queued and is lost: %s", key, json.dumps(payload))

    # ------------------------------------------------------------------ pending retries
    async def run_pending_drainer(self) -> None:
        """Send queued usage again every ``drain_interval_seconds`` until cancelled (runs with the app)."""
        while True:
            try:
                result = await self.drain_pending()
                if result.sent or result.dropped:
                    logger.info(
                        "pending billing usage: %d sent, %d dropped, %d still waiting", result.sent, result.dropped, result.retrying
                    )
            except Exception:
                logger.exception("sending pending billing usage failed")
            await asyncio.sleep(self._drain_interval)

    async def drain_pending(self, *, max_items: int = 200) -> DrainResult:
        """One pass: send up to ``max_items`` queued reports again, oldest first, under the key they were
        queued with. A pass stops at the first report billing can't be reached for; what didn't go through
        goes back to the tail in its order, so the next pass tries it first."""
        result = DrainResult()
        if not self.enabled or self._redis is None:
            return result
        requeue: list[str] = []
        try:
            for _ in range(max_items):
                raw = await self._redis.rpop(PENDING_USAGE_KEY)
                if raw is None:
                    break
                entry = _pending_entry(raw)
                if entry is None:
                    logger.error("dropping an unreadable pending usage entry: %.500s", raw)
                    result.dropped += 1
                    continue
                payload = entry["payload"]
                try:
                    delivery, detail = await self._deliver(payload)
                except asyncio.CancelledError:
                    requeue.append(raw)
                    raise
                if delivery is _Delivery.ACCEPTED:
                    result.sent += 1
                    continue
                if delivery is _Delivery.REFUSED:
                    result.dropped += 1
                    continue
                attempts = int(entry.get("attempts") or 0) + 1
                if attempts >= self._max_attempts:
                    logger.error(
                        "giving up on usage %s after %d attempts (%s): %s", payload["idempotencyKey"], attempts, detail, json.dumps(payload)
                    )
                    result.dropped += 1
                    continue
                requeue.append(json.dumps({**entry, "attempts": attempts, "lastError": detail[:300]}))
                if delivery is _Delivery.UNREACHABLE:
                    break
        finally:
            for raw in reversed(requeue):
                try:
                    await self._redis.rpush(PENDING_USAGE_KEY, raw)
                    result.retrying += 1
                except Exception:
                    logger.error("could not put pending usage back in the queue; it is lost: %.500s", raw)
        return result

    def _headers(self) -> dict[str, str]:
        return {"X-Internal-Token": self._token}


def _read_check(response: httpx.Response) -> CreditCheck | None:
    if response.status_code != 200:
        return None
    try:
        body = response.json()
    except ValueError:
        return None
    if not isinstance(body, dict) or not isinstance(body.get("allowed"), bool):
        return None
    allowed: bool = body["allowed"]
    balance = body.get("balance")
    return CreditCheck(
        allowed=allowed,
        code=str(body.get("code") or ("OK" if allowed else OUT_OF_CREDITS)),
        balance=float(balance) if isinstance(balance, int | float) and not isinstance(balance, bool) else None,
        status=str(body["status"]) if body.get("status") is not None else None,
    )


def _pending_entry(raw: str | bytes) -> dict[str, Any] | None:
    """A queued entry, or ``None`` when it can't be sent. A bare request body (no envelope) is accepted too."""
    try:
        entry = json.loads(raw)
    except (TypeError, ValueError):
        return None
    if isinstance(entry, dict) and "payload" not in entry and "idempotencyKey" in entry:
        entry = {"payload": entry, "attempts": 0}
    payload = entry.get("payload") if isinstance(entry, dict) else None
    if not isinstance(payload, dict) or not payload.get("idempotencyKey") or not payload.get("workspaceId"):
        return None
    return entry
