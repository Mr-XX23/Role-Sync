"""Client for billing-service's internal credit API.

Contract: docs/billing/credit-system-api.md, sections "Internal" and "Python client rules".

``check`` asks whether a workspace may start a paid operation. Allowed answers are cached per
workspace for a few seconds, so a burst of uploads costs one call. When billing-service cannot
answer (unreachable, timeout, 5xx, an unreadable reply) the operation is allowed and a warning is
logged: a billing outage must not stop anyone working.

``charge`` reports usage that already happened, under a stable idempotency key. When
billing-service cannot take it, the request is pushed to the Redis list ``billing:pending_usage``
and a background retrier resends it with the same key, so it is charged exactly once. Nothing here
raises into the caller; if Redis is down too, the charge is logged as lost and the work goes on.

Env: ``BILLING_ENABLED`` (default true; false makes every call a no-op), ``BILLING_SERVICE_URL``
(default http://billing-service:8085), ``INTERNAL_SERVICE_TOKEN``. Optional tuning:
``BILLING_TIMEOUT_SECONDS`` (3), ``BILLING_CHECK_CACHE_SECONDS`` (5),
``BILLING_RETRY_INTERVAL_SECONDS`` (30), ``BILLING_RETRY_MAX_ATTEMPTS`` (720, about six hours),
``BILLING_PENDING_MAX`` (100000). Redis: ``REDIS_URL`` or ``REDIS_HOST``/``REDIS_PORT``/
``REDIS_DB``/``REDIS_PASSWORD``, as the ingestion queue uses.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import threading
import time
import uuid
from dataclasses import dataclass
from typing import Any, Optional

import requests

try:
    import redis as redis_lib
except ImportError:  # pragma: no cover - installed with celery[redis] in the service image
    redis_lib = None

logger = logging.getLogger("billing")

PENDING_USAGE_KEY = "billing:pending_usage"
DEFAULT_BASE_URL = "http://billing-service:8085"

CODE_OK = "OK"
CODE_OUT_OF_CREDITS = "OUT_OF_CREDITS"
CODE_CREDITS_SUSPENDED = "CREDITS_SUSPENDED"

_FALSY = {"0", "false", "no", "off"}

# Worth sending again later, under the same key: any 5xx, timeouts and connection errors (the outage
# the pending queue exists for), and these 4xx. 401/403/404 mean a deploy or configuration problem
# (the internal token, an endpoint not deployed yet) that ops can fix within the retry window; 409 is a
# transient conflict (billing-service answers a same-key race with 200 {"duplicate": true}, never 409).
# Any other 4xx (400, 422) is a malformed report that would fail identically forever: logged, dropped.
# The sales-agent-engine classifies answers exactly the same way - both services drain the same Redis
# list (billing:pending_usage), so each must treat the other's entries alike.
_RETRYABLE_STATUS = frozenset({401, 403, 404, 408, 409, 425, 429})

_SENT = "sent"
_RETRY = "retry"
_DROP = "drop"
# Why a send failed: the service could not be reached at all, or it answered with an error.
_UNREACHABLE = "unreachable"


def _env_float(name: str, default: float) -> float:
    try:
        value = float(os.environ.get(name, "") or default)
        return value if value > 0 else default
    except (TypeError, ValueError):
        return default


def _env_int(name: str, default: int) -> int:
    try:
        value = int(os.environ.get(name, "") or default)
        return value if value > 0 else default
    except (TypeError, ValueError):
        return default


def canonical_uuid(value: Any) -> Optional[str]:
    """The canonical lower-case form of a UUID, or None when ``value`` is not one."""
    if value is None or value == "":
        return None
    try:
        return str(uuid.UUID(str(value).strip()))
    except (ValueError, AttributeError, TypeError):
        return None


@dataclass(frozen=True)
class CreditCheck:
    """billing-service's answer to "may this workspace start a paid operation?"."""

    allowed: bool
    code: str = CODE_OK
    balance: Optional[float] = None
    status: Optional[str] = None
    # Where the answer came from: billing, disabled (BILLING_ENABLED=false), no_workspace (nothing to
    # check against), or fail_open (billing-service could not answer, so the operation is allowed).
    source: str = "billing"


class BillingClient:
    def __init__(
        self,
        *,
        base_url: Optional[str] = None,
        token: Optional[str] = None,
        enabled: Optional[bool] = None,
        timeout_seconds: Optional[float] = None,
        check_cache_seconds: Optional[float] = None,
        retry_interval_seconds: Optional[float] = None,
        max_attempts: Optional[int] = None,
        pending_max: Optional[int] = None,
        http: Any = None,
        redis_client: Any = None,
    ) -> None:
        # Unset options are read from the environment when used, not frozen at import.
        self._base_url = base_url
        self._token = token
        self._enabled = enabled
        self._timeout = timeout_seconds
        self._check_cache_seconds = check_cache_seconds
        self._retry_interval = retry_interval_seconds
        self._max_attempts = max_attempts
        self._pending_max = pending_max
        self._http = http if http is not None else requests
        self._redis = redis_client
        self._redis_injected = redis_client is not None
        self._redis_retry_at = 0.0
        self._cache: dict[str, tuple[float, CreditCheck]] = {}
        self._lock = threading.Lock()
        self._task: Optional[asyncio.Task] = None
        self._running = False

    # ---- configuration ---------------------------------------------------
    @property
    def enabled(self) -> bool:
        if self._enabled is not None:
            return self._enabled
        return os.environ.get("BILLING_ENABLED", "true").strip().lower() not in _FALSY

    @property
    def base_url(self) -> str:
        return (self._base_url or os.environ.get("BILLING_SERVICE_URL", "").strip() or DEFAULT_BASE_URL).rstrip("/")

    @property
    def token(self) -> str:
        return self._token if self._token is not None else os.environ.get("INTERNAL_SERVICE_TOKEN", "").strip()

    @property
    def timeout(self) -> float:
        return self._timeout or _env_float("BILLING_TIMEOUT_SECONDS", 3.0)

    @property
    def check_cache_seconds(self) -> float:
        return self._check_cache_seconds or _env_float("BILLING_CHECK_CACHE_SECONDS", 5.0)

    @property
    def retry_interval_seconds(self) -> float:
        return self._retry_interval or _env_float("BILLING_RETRY_INTERVAL_SECONDS", 30.0)

    @property
    def max_attempts(self) -> int:
        # At the 30 s interval, 720 attempts ride out about six hours of billing-service trouble.
        return self._max_attempts or _env_int("BILLING_RETRY_MAX_ATTEMPTS", 720)

    @property
    def pending_max(self) -> int:
        return self._pending_max or _env_int("BILLING_PENDING_MAX", 100_000)

    def _headers(self) -> dict[str, str]:
        headers = {"Accept": "application/json"}
        if self.token:
            headers["X-Internal-Token"] = self.token
        return headers

    # ---- check -----------------------------------------------------------
    def check(self, workspace_id: Any, user_id: Any = None) -> CreditCheck:
        """Whether the workspace may start a paid operation. Never raises; fails open."""
        try:
            return self._check(workspace_id, user_id)
        except Exception as err:  # a bug here must not block the user's work either
            print(f"[Billing] WARNING credit check crashed ({type(err).__name__}: {err}); allowing.")
            return CreditCheck(True, source="fail_open")

    def _check(self, workspace_id: Any, user_id: Any) -> CreditCheck:
        if not self.enabled:
            return CreditCheck(True, source="disabled")
        workspace = canonical_uuid(workspace_id)
        if workspace is None:
            logger.debug("[Billing] No workspace to check credits for (%r); allowing.", workspace_id)
            return CreditCheck(True, source="no_workspace")

        now = time.monotonic()
        with self._lock:
            cached = self._cache.get(workspace)
        if cached is not None and now - cached[0] < self.check_cache_seconds:
            return cached[1]

        params = {}
        user = canonical_uuid(user_id)
        if user:
            params["userId"] = user
        try:
            response = self._http.get(
                f"{self.base_url}/internal/v1/billing/credits/{workspace}/check",
                params=params or None,
                headers=self._headers(),
                timeout=self.timeout,
            )
        except Exception as err:
            print(f"[Billing] WARNING credit check for workspace {workspace} failed ({type(err).__name__}); allowing (fail open).")
            return self._remember(workspace, now, CreditCheck(True, source="fail_open"))

        status_code = getattr(response, "status_code", 0)
        if status_code != 200:
            print(f"[Billing] WARNING credit check for workspace {workspace} answered HTTP {status_code}; allowing (fail open).")
            return self._remember(workspace, now, CreditCheck(True, source="fail_open"))

        try:
            data = response.json()
            allowed = data.get("allowed")
            if not isinstance(allowed, bool):
                raise ValueError("no 'allowed' flag")
        except Exception as err:
            print(f"[Billing] WARNING unreadable credit check for workspace {workspace} ({err}); allowing (fail open).")
            return self._remember(workspace, now, CreditCheck(True, source="fail_open"))

        code = str(data.get("code") or (CODE_OK if allowed else CODE_OUT_OF_CREDITS))
        balance = data.get("balance")
        result = CreditCheck(
            allowed=allowed,
            code=code,
            balance=float(balance) if isinstance(balance, (int, float)) else None,
            status=data.get("status"),
        )
        return self._remember(workspace, now, result)

    def _remember(self, workspace: str, now: float, result: CreditCheck) -> CreditCheck:
        # Only "allowed" is cached: a workspace that is out of credits is asked again every time, so
        # it is unblocked the moment it buys more. A fail-open answer is cached too, so an outage
        # costs one timeout per workspace per window instead of one per request.
        with self._lock:
            if result.allowed:
                self._cache[workspace] = (now, result)
            else:
                self._cache.pop(workspace, None)
        return result

    def forget(self, workspace_id: Any = None) -> None:
        """Drop cached check answers (one workspace, or all)."""
        with self._lock:
            if workspace_id is None:
                self._cache.clear()
            else:
                self._cache.pop(canonical_uuid(workspace_id) or "", None)

    # ---- charge ----------------------------------------------------------
    def charge(self, payload: dict[str, Any]) -> Optional[dict[str, Any]]:
        """Report usage that already happened (``POST /internal/v1/billing/usage``).

        Returns billing-service's answer, or None when billing is disabled, the charge was queued
        for a retry, or it could not be recorded at all. Never raises.
        """
        try:
            if not self.enabled:
                return None
            body = json.loads(json.dumps(payload, default=str))
            key = body.get("idempotencyKey")
            if not key or not canonical_uuid(body.get("workspaceId")):
                print(f"[Billing] ERROR usage for {body.get('operation')} has no workspace or idempotency key; not recorded.")
                return None

            outcome, detail, reason = self._post_usage(body)
            if outcome == _SENT:
                return detail
            if outcome == _RETRY:
                self._enqueue_pending(body, attempts=1, error=str(detail))
                return None
            print(f"[Billing] ERROR billing-service refused {body.get('operation')} ({key}): {detail}. Not retried.")
            return None
        except Exception as err:
            print(f"[Billing] ERROR could not report usage ({type(err).__name__}: {err}); not recorded.")
            return None

    def _post_usage(self, body: dict[str, Any]) -> tuple[str, Any, str]:
        """Send one usage report. Returns (outcome, answer-or-error, reason)."""
        try:
            response = self._http.post(
                f"{self.base_url}/internal/v1/billing/usage",
                json=body,
                headers=self._headers(),
                timeout=self.timeout,
            )
        except Exception as err:
            return _RETRY, type(err).__name__, _UNREACHABLE

        status_code = getattr(response, "status_code", 0)
        if 200 <= status_code < 300:
            try:
                answer = response.json()
            except Exception:
                answer = {}
            return _SENT, answer if isinstance(answer, dict) else {}, ""
        text = (getattr(response, "text", "") or "")[:200]
        if status_code >= 500 or status_code in _RETRYABLE_STATUS:
            return _RETRY, f"HTTP {status_code} {text}".strip(), "error"
        return _DROP, f"HTTP {status_code} {text}".strip(), "error"

    # ---- pending queue ---------------------------------------------------
    def _redis_client(self) -> Any:
        if self._redis is not None:
            return self._redis
        if self._redis_injected or redis_lib is None:
            return None
        now = time.monotonic()
        if now < self._redis_retry_at:
            return None
        try:
            options = {"decode_responses": True, "socket_connect_timeout": 2, "socket_timeout": 2}
            url = os.environ.get("REDIS_URL", "").strip()
            if url:
                client = redis_lib.Redis.from_url(url, **options)
            else:
                client = redis_lib.Redis(
                    host=os.environ.get("REDIS_HOST", "redis"),
                    port=_env_int("REDIS_PORT", 6379),
                    db=int(os.environ.get("REDIS_DB", "0") or 0),
                    password=os.environ.get("REDIS_PASSWORD", "") or None,
                    **options,
                )
            client.ping()
            self._redis = client
            return client
        except Exception as err:
            # Not retried on every charge: an unreachable Redis would otherwise stall each one.
            self._redis_retry_at = now + 30
            print(f"[Billing] WARNING Redis unavailable for pending usage ({type(err).__name__}).")
            return None

    def _drop_redis(self) -> None:
        if not self._redis_injected:
            self._redis = None
            self._redis_retry_at = time.monotonic() + 30

    def _enqueue_pending(self, body: dict[str, Any], attempts: int, error: str) -> bool:
        key = body.get("idempotencyKey")
        client = self._redis_client()
        if client is None:
            print(
                f"[Billing] ERROR billing-service unavailable ({error}) and Redis unavailable: usage {key} "
                f"({body.get('operation')}, workspace {body.get('workspaceId')}) was not recorded."
            )
            return False
        entry = json.dumps({"payload": body, "attempts": attempts, "lastError": error[:300], "queuedAt": time.time()})
        try:
            if client.llen(PENDING_USAGE_KEY) >= self.pending_max:
                print(f"[Billing] ERROR pending usage queue is full ({self.pending_max}); usage {key} was not recorded.")
                return False
            # Newest at the head, oldest at the tail: drain_pending takes from the tail.
            client.lpush(PENDING_USAGE_KEY, entry)
            print(f"[Billing] WARNING billing-service unavailable ({error}); queued usage {key} for retry.")
            return True
        except Exception as err:
            self._drop_redis()
            print(f"[Billing] ERROR could not queue usage {key} ({type(err).__name__}); it was not recorded.")
            return False

    def pending_count(self) -> int:
        client = self._redis_client()
        if client is None:
            return 0
        try:
            return int(client.llen(PENDING_USAGE_KEY))
        except Exception:
            return 0

    def drain_pending(self, max_items: int = 200) -> dict[str, int]:
        """Resend queued usage once, oldest first, with the key it was queued under.

        A report that fails again goes back on the queue until it has been tried
        ``BILLING_RETRY_MAX_ATTEMPTS`` times, then it is dropped with a log line. A round stops at the
        first report that cannot reach billing-service at all, rather than waiting out a timeout for
        each of the rest.
        """
        stats = {"sent": 0, "requeued": 0, "dropped": 0}
        if not self.enabled:
            return stats
        client = self._redis_client()
        if client is None:
            return stats

        requeue: list[str] = []
        try:
            for _ in range(max(0, max_items)):
                raw = client.rpop(PENDING_USAGE_KEY)
                if raw is None:
                    break
                try:
                    entry = json.loads(raw)
                    body = entry["payload"]
                    attempts = int(entry.get("attempts") or 0)
                except Exception:
                    stats["dropped"] += 1
                    print(f"[Billing] ERROR dropped an unreadable pending usage entry: {str(raw)[:200]}")
                    continue

                outcome, detail, reason = self._post_usage(body)
                if outcome == _SENT:
                    stats["sent"] += 1
                    continue
                key = body.get("idempotencyKey")
                if outcome == _DROP:
                    stats["dropped"] += 1
                    print(f"[Billing] ERROR billing-service refused queued usage {key}: {detail}. Dropped.")
                    continue

                attempts += 1
                if attempts >= self.max_attempts:
                    stats["dropped"] += 1
                    print(
                        f"[Billing] ERROR giving up on usage {key} ({body.get('operation')}, workspace "
                        f"{body.get('workspaceId')}) after {attempts} attempts: {detail}."
                    )
                    continue
                entry["attempts"] = attempts
                entry["lastError"] = str(detail)[:300]
                requeue.append(json.dumps(entry))
                if reason == _UNREACHABLE:
                    break
        except Exception as err:
            self._drop_redis()
            print(f"[Billing] WARNING pending usage drain interrupted ({type(err).__name__}: {err}).")
        finally:
            # Back at the tail, oldest last pushed, so next round retries them first and in order.
            for raw in reversed(requeue):
                try:
                    client.rpush(PENDING_USAGE_KEY, raw)
                    stats["requeued"] += 1
                except Exception as err:
                    print(f"[Billing] ERROR could not requeue pending usage ({type(err).__name__}); it was lost: {raw[:200]}")
        return stats

    # ---- background retrier ----------------------------------------------
    async def start_retrier(self) -> None:
        """Start resending queued usage in the background (called from the FastAPI lifespan)."""
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._retry_loop())
        state = "enabled" if self.enabled else "disabled (BILLING_ENABLED=false)"
        print(f"[Billing] Pending-usage retrier started - billing {state}, every {self.retry_interval_seconds:.0f}s.")

    async def stop_retrier(self) -> None:
        if not self._running:
            return
        self._running = False
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        print("[Billing] Pending-usage retrier stopped.")

    async def _retry_loop(self) -> None:
        while self._running:
            try:
                await asyncio.sleep(self.retry_interval_seconds)
                if not self.enabled:
                    continue
                # Redis and HTTP are blocking calls; keep them off the event loop.
                stats = await asyncio.to_thread(self.drain_pending)
                if any(stats.values()):
                    print(f"[Billing] Pending usage retry: {stats}")
            except asyncio.CancelledError:
                break
            except Exception as err:
                print(f"[Billing] WARNING pending usage retry failed: {err}")


_client = BillingClient()


def get_billing_client() -> BillingClient:
    """The process-wide client. Call sites look it up when they need it, so tests can swap it."""
    return _client


def set_billing_client(client: Any) -> Any:
    """Replace the process-wide client (tests). Returns the previous one."""
    global _client
    previous = _client
    _client = client
    return previous
