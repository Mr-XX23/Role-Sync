"""Only platform super admins reach the engine's Super Admin Console endpoints.

auth-service is the only place that decides who is one, so every check asks its internal API
(``GET /internal/v1/accounts/{authUserId}/platform-access`` with ``X-Internal-Token``). The answer is
cached briefly, like workspace-service's ``PlatformAdminGuard``. Anything that isn't a clear "yes"
refuses the call: 403 for "no", 503 when auth-service can't be asked.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from dataclasses import dataclass
from uuid import UUID

import httpx

from app.core.context import Principal
from app.core.errors import AuthenticationFailed, EngineError, UpstreamUnavailable

logger = logging.getLogger(__name__)

NOT_SUPER_ADMIN = "Only platform super admins can do this."
_MAX_CACHED = 1000


class NotSuperAdmin(EngineError):
    status_code = 403
    code = "NOT_SUPER_ADMIN"


@dataclass(frozen=True, slots=True)
class AdminActor:
    """The signed-in platform super admin: who they are, for the audit log."""

    user_id: UUID
    email: str | None


class PlatformAccessClient:
    def __init__(self, *, base_url: str, token: str | None, http: httpx.AsyncClient, timeout_seconds: float = 10.0) -> None:
        self._url = base_url.rstrip("/")
        self._token = (token or "").strip()
        self._http = http
        self._timeout = timeout_seconds

    async def platform_access(self, user_id: UUID) -> tuple[bool, str | None]:
        """``(super_admin, email)``. Raises ``UpstreamUnavailable`` when auth-service can't answer."""
        if not self._token:
            raise UpstreamUnavailable(
                "The Super Admin Console isn't set up yet: INTERNAL_SERVICE_TOKEN is missing on the server."
            )
        try:
            response = await self._http.get(
                f"{self._url}/internal/v1/accounts/{user_id}/platform-access",
                headers={"X-Internal-Token": self._token},
                timeout=self._timeout,
            )
        except httpx.HTTPError as exc:
            logger.error("auth-service platform-access check failed for %s: %s", user_id, exc)
            raise UpstreamUnavailable(
                "The account service is unavailable right now, so your access can't be checked. Try again in a moment."
            ) from exc
        if response.status_code == 404:
            return False, None
        if response.status_code in (401, 403, 503):
            logger.error(
                "auth-service refused the internal platform-access call (%s): check INTERNAL_SERVICE_TOKEN", response.status_code
            )
            raise UpstreamUnavailable("The Super Admin Console isn't set up correctly: the account service rejected this server.")
        if response.status_code != 200:
            logger.error("auth-service platform-access check for %s answered %s", user_id, response.status_code)
            raise UpstreamUnavailable("The account service is unavailable right now. Try again in a moment.")
        try:
            body = response.json()
        except ValueError as exc:
            raise UpstreamUnavailable("The account service gave an unreadable answer. Try again in a moment.") from exc
        return body.get("superAdmin") is True, body.get("email")


class PlatformAdminGuard:
    def __init__(
        self, client: PlatformAccessClient, *, ttl_seconds: float = 30.0, clock: Callable[[], float] = time.monotonic
    ) -> None:
        self._client = client
        self._ttl = ttl_seconds
        self._clock = clock
        self._cache: dict[UUID, tuple[bool, str | None, float]] = {}

    async def require_super_admin(self, principal: Principal | None) -> AdminActor:
        if principal is None:
            raise AuthenticationFailed("Your session has ended. Sign in again.")
        now = self._clock()
        cached = self._cache.get(principal.user_id)
        if cached is None or cached[2] <= now:
            super_admin, email = await self._client.platform_access(principal.user_id)  # failures are never cached
            cached = (super_admin, email, now + self._ttl)
            if len(self._cache) >= _MAX_CACHED:
                self._cache = {key: value for key, value in self._cache.items() if value[2] > now}
            self._cache[principal.user_id] = cached
        if not cached[0]:
            logger.warning("refused Super Admin Console call by account %s", principal.user_id)
            raise NotSuperAdmin(NOT_SUPER_ADMIN)
        return AdminActor(user_id=principal.user_id, email=cached[1] or principal.email)
