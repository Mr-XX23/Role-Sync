"""An in-memory billing-service (the internal credit check and usage routes) behind an httpx MockTransport,
answering like docs/billing/credit-system-api.md, and a small in-memory Redis with the commands the billing
client uses."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

import httpx

from app.billing.client import BillingClient

BILLING_URL = "http://billing.test"


@dataclass
class FakeBillingService:
    answers: dict[UUID, dict[str, Any]] = field(default_factory=dict)  # workspace → check answer (default: allowed)
    # What the next requests get instead: a status code, an exception to raise, or a non-JSON 200 body.
    fail_next: list[int | Exception | str] = field(default_factory=list)
    down: bool = False  # every request fails to connect
    lose_responses: bool = False  # usage is charged, but the answer never arrives (a timeout)
    balance_after_charge: float = 11.25  # the balance a usage answer reports (at or below zero: the credits ran out)
    requests: list[httpx.Request] = field(default_factory=list)  # every request, retries included
    charged: dict[str, dict[str, Any]] = field(default_factory=dict)  # idempotency key → body: what billing kept

    def refuse(self, workspace_id: UUID, code: str = "OUT_OF_CREDITS") -> None:
        status = "SUSPENDED" if code == "CREDITS_SUSPENDED" else "ACTIVE"
        self.answers[workspace_id] = {"allowed": False, "code": code, "balance": -2.5, "status": status}

    def usage_requests(self) -> list[dict[str, Any]]:
        return [json.loads(request.content) for request in self.requests if request.url.path == "/internal/v1/billing/usage"]

    def charges(self, operation: str | None = None) -> list[dict[str, Any]]:
        return [body for body in self.charged.values() if operation is None or body["operation"] == operation]

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if self.down:
            raise httpx.ConnectError("billing-service is down")
        if self.fail_next:
            failure = self.fail_next.pop(0)
            if isinstance(failure, Exception):
                raise failure
            if isinstance(failure, str):
                return httpx.Response(200, text=failure)
            return httpx.Response(failure, json={"code": "INJECTED", "error": "injected failure"})
        path = request.url.path
        if request.method == "GET" and path.startswith("/internal/v1/billing/credits/") and path.endswith("/check"):
            workspace_id = UUID(path.split("/")[-2])
            answer = self.answers.get(workspace_id, {"allowed": True, "code": "OK", "balance": 12.5, "status": "ACTIVE"})
            return httpx.Response(200, json=answer)
        if request.method == "POST" and path == "/internal/v1/billing/usage":
            body = json.loads(request.content)
            duplicate = body["idempotencyKey"] in self.charged
            self.charged.setdefault(body["idempotencyKey"], body)
            if self.lose_responses:
                raise httpx.ReadTimeout("the answer was lost")
            return httpx.Response(
                200,
                json={
                    "creditsCharged": 0 if duplicate else 1.25,
                    "costUsd": 0.0021,
                    "balance": self.balance_after_charge,
                    "status": "ACTIVE",
                    "duplicate": duplicate,
                },
            )
        return httpx.Response(404, json={"error": "not found"})

    def transport(self) -> httpx.MockTransport:
        return httpx.MockTransport(self.handler)

    def client(self, redis: FakeRedis | None = None, **options: Any) -> BillingClient:
        options.setdefault("token", "internal-test-token")
        return BillingClient(base_url=BILLING_URL, http=httpx.AsyncClient(transport=self.transport()), redis=redis, **options)


class FakeRedis:
    """Redis lists, with ``decode_responses=True`` semantics (strings in, strings out). Index 0 is the head."""

    def __init__(self) -> None:
        self.lists: dict[str, list[str]] = {}

    async def lpush(self, key: str, *values: str) -> int:
        items = self.lists.setdefault(key, [])
        for value in values:
            items.insert(0, str(value))
        return len(items)

    async def rpush(self, key: str, *values: str) -> int:
        items = self.lists.setdefault(key, [])
        items.extend(str(value) for value in values)
        return len(items)

    async def rpop(self, key: str) -> str | None:
        items = self.lists.get(key)
        return items.pop() if items else None

    async def llen(self, key: str) -> int:
        return len(self.lists.get(key, []))
