"""A stand-in for billing-service, installed as the process-wide billing client.

It answers credit checks from a script and records every usage report, de-duplicating them by
idempotency key the way billing-service does - so a test can assert what a workspace was actually
charged, not just what was sent.

    from tests.fake_billing import billing  # the fixture

    def test_something(billing):
        billing.deny("OUT_OF_CREDITS")
        ...
        assert billing.of("document.ingest") == [...]
"""
from __future__ import annotations

from typing import Any, Optional

import pytest

from billing.client import CODE_OK, CreditCheck, set_billing_client


class FakeBillingClient:
    enabled = True

    def __init__(self) -> None:
        self.allowed = True
        self.code = CODE_OK
        self.checks: list[tuple[Any, Any]] = []
        self.charges: list[dict[str, Any]] = []  # every report received, duplicates included

    # ---- scripting -----------------------------------------------------
    def deny(self, code: str = "OUT_OF_CREDITS") -> None:
        self.allowed, self.code = False, code

    def allow(self) -> None:
        self.allowed, self.code = True, CODE_OK

    # ---- the client's interface ----------------------------------------
    def check(self, workspace_id: Any, user_id: Any = None) -> CreditCheck:
        self.checks.append((workspace_id, user_id))
        return CreditCheck(True) if self.allowed else CreditCheck(False, code=self.code)

    def charge(self, payload: dict[str, Any]) -> Optional[dict[str, Any]]:
        duplicate = any(c["idempotencyKey"] == payload["idempotencyKey"] for c in self.charges)
        self.charges.append(payload)
        return {"creditsCharged": 0 if duplicate else 1, "duplicate": duplicate}

    async def start_retrier(self) -> None:
        return None

    async def stop_retrier(self) -> None:
        return None

    # ---- reading -------------------------------------------------------
    @property
    def billed(self) -> list[dict[str, Any]]:
        """What billing-service would have charged: the first report for each key."""
        seen: set[str] = set()
        billed = []
        for charge in self.charges:
            if charge["idempotencyKey"] not in seen:
                seen.add(charge["idempotencyKey"])
                billed.append(charge)
        return billed

    def of(self, operation: str) -> list[dict[str, Any]]:
        return [charge for charge in self.billed if charge["operation"] == operation]


def items_by_kind(charge: dict[str, Any]) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
    """({model: TOKENS item}, {unit: quantity}) of one usage report."""
    tokens = {item["model"]: item for item in charge["items"] if item["type"] == "TOKENS"}
    units = {item["unit"]: item["quantity"] for item in charge["items"] if item["type"] == "UNITS"}
    return tokens, units


@pytest.fixture
def billing():
    fake = FakeBillingClient()
    previous = set_billing_client(fake)
    try:
        yield fake
    finally:
        set_billing_client(previous)
