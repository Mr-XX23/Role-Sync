"""The billing-service client: checks that fail open, the short allowed-answer cache, charges, and the
Redis queue that resends usage billing couldn't take, under the same idempotency key."""

from __future__ import annotations

import asyncio
import json
import logging
from uuid import uuid4

import httpx
import pytest

from app.billing.client import PENDING_USAGE_KEY, BillingClient, TokensItem, UnitsItem, UsageCharge
from tests.fake_billing import BILLING_URL, FakeBillingService, FakeRedis

WORKSPACE, USER = uuid4(), uuid4()


class Clock:
    def __init__(self) -> None:
        self.now = 1_000.0

    def __call__(self) -> float:
        return self.now


def _usage(**overrides) -> UsageCharge:
    fields = {
        "workspace_id": WORKSPACE,
        "user_id": USER,
        "operation": "agent.model_call",
        "category": "AGENT",
        "items": (TokensItem(model="gemini-3.5-flash", input_tokens=18_000, cached_input_tokens=12_000, output_tokens=800),),
        "reference": "session-1",
        "metadata": {"purpose": "plan", "provider": "gemini"},
    }
    return UsageCharge(**(fields | overrides))


def _entries(redis: FakeRedis) -> list[dict]:
    """The queue from head (newest) to tail (next to be retried)."""
    return [json.loads(raw) for raw in redis.lists.get(PENDING_USAGE_KEY, [])]


def _queued(redis: FakeRedis) -> list[dict]:
    return [entry["payload"] for entry in _entries(redis)]


# --------------------------------------------------------------------------- check


async def test_a_check_asks_billing_with_the_internal_token_and_reads_its_answer():
    billing = FakeBillingService()
    billing.refuse(WORKSPACE, "CREDITS_SUSPENDED")

    check = await billing.client().check(WORKSPACE, USER)

    [request] = billing.requests
    assert request.url.path == f"/internal/v1/billing/credits/{WORKSPACE}/check"
    assert request.url.params["userId"] == str(USER)
    assert request.headers["X-Internal-Token"] == "internal-test-token"
    assert (check.allowed, check.code, check.status, check.balance, check.verified) == (False, "CREDITS_SUSPENDED", "SUSPENDED", -2.5, True)
    assert check.message == "Credits for this workspace are suspended. Contact support."


async def test_allowed_answers_are_cached_for_a_few_seconds_per_workspace_and_refusals_never():
    billing, clock = FakeBillingService(), Clock()
    client = billing.client(clock=clock)

    assert (await client.check(WORKSPACE, USER)).allowed
    clock.now += 4.9
    assert (await client.check(WORKSPACE, USER)).allowed
    assert len(billing.requests) == 1  # a burst of requests asks billing once
    await client.check(uuid4(), USER)
    assert len(billing.requests) == 2  # the cache is per workspace

    clock.now += 0.2  # past 5 seconds: billing is asked again
    billing.refuse(WORKSPACE)
    refused = await client.check(WORKSPACE, USER)
    assert not refused.allowed and refused.code == "OUT_OF_CREDITS"
    assert refused.message == "Your workspace is out of credits. Buy more credits to keep using the assistant."
    assert len(billing.requests) == 3

    del billing.answers[WORKSPACE]  # credits bought a moment later count at once: a refusal isn't cached
    assert (await client.check(WORKSPACE, USER)).allowed
    assert len(billing.requests) == 4


async def test_a_charge_that_uses_up_the_balance_ends_the_cached_allowed_answer():
    billing = FakeBillingService()
    client = billing.client()
    assert (await client.check(WORKSPACE, USER)).allowed

    await client.charge(_usage())  # 11.25 left: the cached answer still stands
    await client.check(WORKSPACE, USER)
    assert len(billing.requests) == 2

    billing.balance_after_charge = -0.75  # this charge took the workspace below zero
    await client.charge(_usage())
    billing.refuse(WORKSPACE)
    refused = await client.check(WORKSPACE, USER)  # asked again at once, not after the cache runs out

    assert not refused.allowed and len(billing.requests) == 4


@pytest.mark.parametrize(
    "failure",
    [httpx.ConnectError("refused"), httpx.ReadTimeout("slow"), 500, 503, 401, "<html>gateway error</html>"],
    ids=["unreachable", "timeout", "500", "503", "401", "not-json"],
)
async def test_a_check_fails_open_when_billing_is_unreachable_or_erroring(failure, caplog):
    billing, clock = FakeBillingService(fail_next=[failure]), Clock()
    client = billing.client(clock=clock)

    with caplog.at_level(logging.WARNING, logger="app.billing.client"):
        check = await client.check(WORKSPACE, USER)

    assert check.allowed and not check.verified
    assert "failed open" in caplog.text
    await client.check(WORKSPACE, USER)
    assert len(billing.requests) == 1  # an outage costs one wait per workspace per few seconds, not one per request
    clock.now += 5.1
    assert (await client.check(WORKSPACE, USER)).verified  # then billing is asked again
    assert len(billing.requests) == 2


# --------------------------------------------------------------------------- charge


async def test_a_charge_posts_the_usage_body_of_the_contract():
    billing = FakeBillingService()
    usage = _usage(items=(TokensItem("gemini-2.5-flash", 900, 0, 120), UnitsItem("GROUNDED_PROMPT_25")))

    await billing.client().charge(usage)

    [request] = billing.requests
    assert (request.method, request.url.path) == ("POST", "/internal/v1/billing/usage")
    assert request.headers["X-Internal-Token"] == "internal-test-token"
    assert json.loads(request.content) == {
        "workspaceId": str(WORKSPACE),
        "userId": str(USER),
        "operation": "agent.model_call",
        "category": "AGENT",
        "idempotencyKey": usage.idempotency_key,
        "reference": "session-1",
        "items": [
            {"type": "TOKENS", "model": "gemini-2.5-flash", "inputTokens": 900, "cachedInputTokens": 0, "outputTokens": 120},
            {"type": "UNITS", "unit": "GROUNDED_PROMPT_25", "quantity": 1},
        ],
        "metadata": {"purpose": "plan", "provider": "gemini"},
    }
    assert usage.idempotency_key.startswith("sales-agent-engine:") and _usage().idempotency_key != usage.idempotency_key


async def test_usage_billing_cannot_take_waits_in_redis_and_is_resent_later_under_the_same_key():
    billing, redis = FakeBillingService(down=True), FakeRedis()
    client = billing.client(redis)
    usage = _usage()

    await client.charge(usage)  # never raises into the metered work

    [entry] = _entries(redis)
    assert entry["payload"] == usage.to_json() and entry["attempts"] == 1
    assert entry["lastError"] == "ConnectError" and isinstance(entry["queuedAt"], float)
    assert (await client.drain_pending()).retrying == 1  # still down: back in the queue
    assert _entries(redis)[0]["attempts"] == 2

    billing.down = False
    result = await client.drain_pending()

    assert (result.sent, result.retrying, result.dropped) == (1, 0, 0)
    assert _entries(redis) == []
    assert [body["idempotencyKey"] for body in billing.usage_requests()] == [usage.idempotency_key] * 3
    assert list(billing.charged) == [usage.idempotency_key]


async def test_a_retry_of_usage_billing_already_recorded_does_not_charge_it_twice():
    billing, redis = FakeBillingService(lose_responses=True), FakeRedis()
    client = billing.client(redis)

    await client.charge(_usage())  # charged, but the answer timed out: queued to be sure
    billing.lose_responses = False
    assert (await client.drain_pending()).sent == 1

    assert len(billing.usage_requests()) == 2 and len(billing.charged) == 1


@pytest.mark.parametrize(
    ("status", "retried"),
    [(500, True), (503, True), (409, True), (429, True), (401, True), (403, True), (404, True), (400, False), (413, False), (422, False)],
)
async def test_server_and_deploy_errors_are_retried_and_malformed_requests_are_dropped(status, retried, caplog):
    billing, redis = FakeBillingService(fail_next=[status]), FakeRedis()

    with caplog.at_level(logging.WARNING, logger="app.billing.client"):
        await billing.client(redis).charge(_usage())

    assert len(_queued(redis)) == (1 if retried else 0)
    if not retried:
        assert "refused usage" in caplog.text and "dropping it" in caplog.text and '"operation": "agent.model_call"' in caplog.text


async def test_queued_usage_is_given_up_only_after_its_attempts_are_used(caplog):
    billing, redis = FakeBillingService(down=True), FakeRedis()
    client = billing.client(redis, max_attempts=3)
    usage = _usage()
    await client.charge(usage)  # attempt 1

    assert (await client.drain_pending()).retrying == 1  # attempt 2
    with caplog.at_level(logging.ERROR, logger="app.billing.client"):
        result = await client.drain_pending()  # attempt 3: given up

    assert result.dropped == 1 and _entries(redis) == []
    assert f"giving up on usage {usage.idempotency_key} after 3 attempts" in caplog.text


async def test_a_pass_takes_the_oldest_first_stops_when_billing_is_unreachable_and_keeps_the_order():
    billing, redis = FakeBillingService(down=True), FakeRedis()
    client = billing.client(redis)
    older, newer = _usage(), _usage()
    await client.charge(older)
    await client.charge(newer)
    billing.requests.clear()

    await client.drain_pending()

    assert [json.loads(request.content)["idempotencyKey"] for request in billing.requests] == [older.idempotency_key]
    assert [body["idempotencyKey"] for body in _queued(redis)] == [newer.idempotency_key, older.idempotency_key]
    billing.down = False
    await client.drain_pending()
    assert list(billing.charged) == [older.idempotency_key, newer.idempotency_key]


async def test_entries_queued_by_the_data_pipeline_client_are_sent_and_unreadable_ones_dropped():
    billing, redis = FakeBillingService(), FakeRedis()
    theirs = {
        "payload": {
            "workspaceId": str(WORKSPACE),
            "userId": None,
            "operation": "document.ingest",
            "category": "DOCUMENTS",
            "idempotencyKey": "doc-42:ingest",
            "reference": "doc-42",
            "items": [{"type": "UNITS", "unit": "LLAMAPARSE_PAGE", "quantity": 8}],
            "metadata": {},
        },
        "attempts": 4,
        "lastError": "HTTP 503",
        "queuedAt": 1_789_000_000.0,
    }
    bare = _usage().to_json()  # a request body without the envelope is sent too
    redis.lists[PENDING_USAGE_KEY] = ["not json", json.dumps({"attempts": 1}), json.dumps(bare), json.dumps(theirs)]

    result = await billing.client(redis).drain_pending()

    assert (result.sent, result.dropped) == (2, 2)
    assert list(billing.charged) == ["doc-42:ingest", bare["idempotencyKey"]] and _entries(redis) == []


async def test_the_queue_has_a_ceiling(caplog):
    billing, redis = FakeBillingService(down=True), FakeRedis()
    client = billing.client(redis, pending_max=2)

    with caplog.at_level(logging.ERROR, logger="app.billing.client"):
        for _ in range(3):
            await client.charge(_usage())

    assert len(_entries(redis)) == 2 and "the pending usage queue is full (2)" in caplog.text


async def test_the_background_drainer_resends_queued_usage():
    billing, redis = FakeBillingService(down=True), FakeRedis()
    client = billing.client(redis, drain_interval_seconds=0.01)
    await client.charge(_usage())
    billing.down = False

    drainer = asyncio.create_task(client.run_pending_drainer())
    try:
        for _ in range(200):
            if billing.charged:
                break
            await asyncio.sleep(0.01)
    finally:
        drainer.cancel()
        await asyncio.gather(drainer, return_exceptions=True)

    assert len(billing.charged) == 1 and _entries(redis) == []


async def test_background_charges_never_hold_the_caller_and_shutdown_queues_what_is_unfinished():
    started = asyncio.Event()

    async def never_answers(request: httpx.Request) -> httpx.Response:
        started.set()
        await asyncio.Event().wait()
        raise AssertionError("unreachable")

    redis = FakeRedis()
    client = BillingClient(
        base_url=BILLING_URL, token="t", http=httpx.AsyncClient(transport=httpx.MockTransport(never_answers)), redis=redis
    )
    usage = _usage()

    client.submit(usage)  # returns at once
    await asyncio.wait_for(started.wait(), 2)
    await client.aclose(grace_seconds=0.05)

    assert _queued(redis) == [usage.to_json()]  # the next process sends it, same key


async def test_disabled_billing_allows_everything_and_charges_nothing():
    billing, redis = FakeBillingService(), FakeRedis()
    billing.refuse(WORKSPACE)
    client = billing.client(redis, enabled=False)

    check = await client.check(WORKSPACE, USER)
    await client.charge(_usage())
    client.submit(_usage())
    await client.flush()
    result = await client.drain_pending()

    assert check.allowed and not check.verified
    assert (result.sent, result.retrying, result.dropped) == (0, 0, 0)
    assert billing.requests == [] and redis.lists == {}
