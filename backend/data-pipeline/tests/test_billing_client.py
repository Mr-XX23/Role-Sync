"""The billing-service client: credit checks fail open, charges are never lost or doubled.

billing-service is not running in unit tests: HTTP and Redis are fakes injected into the client.
"""
import asyncio
import json
import uuid

import pytest
import requests

from billing import client as client_module
from billing.client import PENDING_USAGE_KEY, BillingClient
from tests.fake_redis import FakeRedis

WORKSPACE = str(uuid.uuid4())
OTHER_WORKSPACE = str(uuid.uuid4())
USER = str(uuid.uuid4())
KEY = f"document.ingest:doc_1:0123456789abcdef:{uuid.uuid4().hex}:index"


class FakeResponse:
    def __init__(self, status_code=200, body=None, text=""):
        self.status_code = status_code
        self._body = body
        self.text = text or (json.dumps(body) if isinstance(body, (dict, list)) else "")

    def json(self):
        if isinstance(self._body, Exception) or self._body is None:
            raise ValueError("not json")
        return self._body


class FakeHttp:
    """Scripted answers for GET (checks) and POST (usage); the last answer repeats."""

    def __init__(self, get=None, post=None):
        self.get_script = list(get or [])
        self.post_script = list(post or [])
        self.gets = []
        self.posts = []

    @staticmethod
    def _next(script, calls):
        item = script[min(len(calls) - 1, len(script) - 1)]
        if isinstance(item, BaseException):
            raise item
        return item

    def get(self, url, params=None, headers=None, timeout=None):
        self.gets.append({"url": url, "params": params, "headers": headers, "timeout": timeout})
        return self._next(self.get_script, self.gets)

    def post(self, url, json=None, headers=None, timeout=None):
        self.posts.append({"url": url, "json": json, "headers": headers, "timeout": timeout})
        return self._next(self.post_script, self.posts)


def make_client(http, redis=None, **options):
    return BillingClient(
        base_url="http://billing.test", token="internal-secret", enabled=True, http=http,
        redis_client=redis if redis is not None else FakeRedis(), **options,
    )


def usage_payload(key=KEY, workspace=WORKSPACE):
    return {
        "workspaceId": workspace,
        "userId": USER,
        "operation": "document.ingest",
        "category": "DOCUMENTS",
        "idempotencyKey": key,
        "reference": "doc_1",
        "items": [{"type": "UNITS", "unit": "LLAMAPARSE_PAGE", "quantity": 8}],
        "metadata": {"stage": "index"},
    }


def allowed(balance=12.5):
    return FakeResponse(200, {"allowed": True, "code": "OK", "balance": balance, "status": "ACTIVE"})


def queued(redis):
    return [json.loads(raw) for raw in redis.lrange(PENDING_USAGE_KEY, 0, -1)]


# =========================================================================
# check
# =========================================================================
def test_a_check_asks_billing_service_with_the_internal_token_and_the_user():
    http = FakeHttp(get=[allowed()])

    result = make_client(http).check(WORKSPACE.upper(), USER)

    assert result.allowed and result.code == "OK" and result.balance == 12.5 and result.status == "ACTIVE"
    call = http.gets[0]
    assert call["url"] == f"http://billing.test/internal/v1/billing/credits/{WORKSPACE}/check"
    assert call["params"] == {"userId": USER}
    assert call["headers"]["X-Internal-Token"] == "internal-secret"
    assert call["timeout"] == 3.0


def test_a_user_id_that_is_not_a_uuid_is_left_out_of_the_check():
    http = FakeHttp(get=[allowed()])

    make_client(http).check(WORKSPACE, "user_a")

    assert http.gets[0]["params"] is None


@pytest.mark.parametrize("code", ["OUT_OF_CREDITS", "CREDITS_SUSPENDED"])
def test_a_refusal_comes_back_with_its_code(code):
    http = FakeHttp(get=[FakeResponse(200, {"allowed": False, "code": code, "balance": 0, "status": "ACTIVE"})])

    result = make_client(http).check(WORKSPACE, USER)

    assert not result.allowed and result.code == code


def test_allowed_answers_are_cached_per_workspace_for_a_few_seconds(monkeypatch):
    clock = [1000.0]
    monkeypatch.setattr(client_module.time, "monotonic", lambda: clock[0])
    http = FakeHttp(get=[allowed()])
    client = make_client(http)

    client.check(WORKSPACE, USER)
    client.check(WORKSPACE, str(uuid.uuid4()))  # any member of the workspace
    assert len(http.gets) == 1

    client.check(OTHER_WORKSPACE, USER)
    assert len(http.gets) == 2

    clock[0] += 5.5
    client.check(WORKSPACE, USER)
    assert len(http.gets) == 3


def test_refusals_are_not_cached_so_buying_credits_takes_effect_at_once():
    http = FakeHttp(get=[FakeResponse(200, {"allowed": False, "code": "OUT_OF_CREDITS"}), allowed()])
    client = make_client(http)

    assert not client.check(WORKSPACE, USER).allowed
    assert client.check(WORKSPACE, USER).allowed
    assert len(http.gets) == 2


@pytest.mark.parametrize(
    "failure",
    [
        requests.ConnectionError("connection refused"),
        requests.Timeout("read timed out"),
        FakeResponse(500),
        FakeResponse(503),
        FakeResponse(401),
        FakeResponse(200, ValueError("not json")),
        FakeResponse(200, {"unexpected": True}),
    ],
    ids=["refused", "timeout", "500", "503", "401", "not-json", "no-allowed-flag"],
)
def test_a_check_billing_service_cannot_answer_allows_the_work(failure, capsys):
    result = make_client(FakeHttp(get=[failure])).check(WORKSPACE, USER)

    assert result.allowed and result.source == "fail_open"
    assert "WARNING" in capsys.readouterr().out


def test_an_outage_costs_one_attempt_per_workspace_per_cache_window():
    http = FakeHttp(get=[requests.Timeout("read timed out")])
    client = make_client(http)

    for _ in range(5):
        assert client.check(WORKSPACE, USER).allowed
    assert len(http.gets) == 1


def test_work_without_a_workspace_is_not_checked():
    http = FakeHttp(get=[allowed()])

    result = make_client(http).check("tenant_default", USER)

    assert result.allowed and result.source == "no_workspace"
    assert http.gets == []


def test_disabled_billing_never_calls_billing_service_or_redis(monkeypatch):
    monkeypatch.setenv("BILLING_ENABLED", "false")
    http, redis = FakeHttp(get=[allowed()], post=[FakeResponse(200, {})]), FakeRedis()
    client = BillingClient(http=http, redis_client=redis)

    assert client.check(WORKSPACE, USER).source == "disabled"
    assert client.charge(usage_payload()) is None
    assert client.drain_pending() == {"sent": 0, "requeued": 0, "dropped": 0}
    assert http.gets == [] and http.posts == [] and redis.lists == {}


def test_configuration_comes_from_the_environment(monkeypatch):
    for name in ("BILLING_ENABLED", "BILLING_SERVICE_URL", "INTERNAL_SERVICE_TOKEN"):
        monkeypatch.delenv(name, raising=False)
    client = BillingClient()
    assert client.enabled is True
    assert client.base_url == "http://billing-service:8085"
    assert client.token == ""

    monkeypatch.setenv("BILLING_SERVICE_URL", "http://billing.internal:9000/")
    monkeypatch.setenv("INTERNAL_SERVICE_TOKEN", "t0k3n")
    monkeypatch.setenv("BILLING_ENABLED", "FALSE")
    assert (client.base_url, client.token, client.enabled) == ("http://billing.internal:9000", "t0k3n", False)


# =========================================================================
# charge
# =========================================================================
def test_a_charge_is_posted_with_the_internal_token():
    http = FakeHttp(post=[FakeResponse(200, {"creditsCharged": 13.2, "balance": 474.0, "duplicate": False})])

    answer = make_client(http).charge(usage_payload())

    assert answer["creditsCharged"] == 13.2
    call = http.posts[0]
    assert call["url"] == "http://billing.test/internal/v1/billing/usage"
    assert call["json"] == usage_payload()
    assert call["headers"]["X-Internal-Token"] == "internal-secret"
    assert call["timeout"] == 3.0


# The same classification as the sales-agent-engine's client: both drain billing:pending_usage.
RETRYABLE_STATUSES = (500, 502, 503, 504, 401, 403, 404, 408, 409, 425, 429)


@pytest.mark.parametrize(
    "failure",
    [requests.ConnectionError("refused"), requests.Timeout("slow"), *(FakeResponse(status) for status in RETRYABLE_STATUSES)],
    ids=["refused", "timeout", *(str(status) for status in RETRYABLE_STATUSES)],
)
def test_a_charge_billing_service_cannot_take_waits_in_redis_under_its_key(failure):
    redis = FakeRedis()

    assert make_client(FakeHttp(post=[failure]), redis=redis).charge(usage_payload()) is None

    [entry] = queued(redis)
    assert entry["payload"] == usage_payload()
    assert entry["attempts"] == 1
    assert set(entry) == {"payload", "attempts", "lastError", "queuedAt"}


@pytest.mark.parametrize("status", [400, 413, 422])
def test_a_malformed_charge_is_logged_and_dropped(status, capsys):
    redis = FakeRedis()

    make_client(FakeHttp(post=[FakeResponse(status, text="bad item")]), redis=redis).charge(usage_payload())

    assert queued(redis) == []
    assert "ERROR" in capsys.readouterr().out


def test_a_conflict_is_retried_rather_than_taken_as_recorded():
    """billing-service answers a same-key race with 200 {"duplicate": true}; a 409 is transient."""
    redis = FakeRedis()
    http = FakeHttp(post=[FakeResponse(409)])
    client = make_client(http, redis=redis)
    client.charge(usage_payload())

    assert client.drain_pending() == {"sent": 0, "requeued": 1, "dropped": 0}
    http.post_script = [FakeResponse(200, {"duplicate": True})]
    assert client.drain_pending() == {"sent": 1, "requeued": 0, "dropped": 0}
    assert queued(redis) == []


def test_a_charge_never_raises_even_when_redis_is_down_too(capsys):
    class DownRedis:
        def __getattr__(self, name):
            def fail(*args, **kwargs):
                raise ConnectionError("redis is down")

            return fail

    client = make_client(FakeHttp(post=[requests.ConnectionError("refused")]), redis=DownRedis())

    assert client.charge(usage_payload()) is None
    assert "was not recorded" in capsys.readouterr().out


def test_a_charge_without_a_workspace_or_key_is_not_sent():
    http = FakeHttp(post=[FakeResponse(200, {})])
    client = make_client(http)

    client.charge(usage_payload(workspace="tenant_default"))
    client.charge(usage_payload(key=""))

    assert http.posts == []


# =========================================================================
# pending usage retries
# =========================================================================
def test_a_queued_charge_is_resent_with_the_same_key_and_removed_once_recorded():
    redis = FakeRedis()
    http = FakeHttp(post=[requests.ConnectionError("down"), FakeResponse(200, {"duplicate": False})])
    client = make_client(http, redis=redis)
    client.charge(usage_payload())

    assert client.drain_pending() == {"sent": 1, "requeued": 0, "dropped": 0}
    assert queued(redis) == []
    assert [call["json"]["idempotencyKey"] for call in http.posts] == [KEY, KEY]


def test_a_resend_that_fails_again_goes_back_with_its_attempt_count():
    redis = FakeRedis()
    client = make_client(FakeHttp(post=[FakeResponse(503)]), redis=redis)
    client.charge(usage_payload())

    assert client.drain_pending() == {"sent": 0, "requeued": 1, "dropped": 0}
    assert [entry["attempts"] for entry in queued(redis)] == [2]


def test_a_charge_is_dropped_with_a_log_line_after_the_last_attempt(capsys):
    redis = FakeRedis()
    client = make_client(FakeHttp(post=[FakeResponse(503)]), redis=redis, max_attempts=3)
    client.charge(usage_payload())

    client.drain_pending()  # attempt 2
    assert client.drain_pending() == {"sent": 0, "requeued": 0, "dropped": 1}  # attempt 3
    assert queued(redis) == []
    assert "giving up on usage" in capsys.readouterr().out


def test_a_round_stops_at_the_first_charge_that_cannot_reach_billing_service():
    redis = FakeRedis()
    http = FakeHttp(post=[requests.ConnectionError("down")])
    client = make_client(http, redis=redis)
    for n in range(3):
        client.charge(usage_payload(key=f"{KEY}-{n}"))
    http.posts.clear()

    client.drain_pending()

    assert len(http.posts) == 1  # not a timeout per queued charge
    assert len(queued(redis)) == 3


def test_queued_charges_are_resent_oldest_first():
    redis = FakeRedis()
    http = FakeHttp(post=[requests.ConnectionError("down")])
    client = make_client(http, redis=redis)
    for n in range(3):
        client.charge(usage_payload(key=f"{KEY}-{n}"))
    http.post_script = [FakeResponse(200, {})]
    http.posts.clear()

    assert client.drain_pending()["sent"] == 3
    assert [call["json"]["idempotencyKey"] for call in http.posts] == [f"{KEY}-0", f"{KEY}-1", f"{KEY}-2"]


def test_the_background_retrier_resends_queued_charges():
    redis = FakeRedis()
    http = FakeHttp(post=[requests.ConnectionError("down")])
    client = make_client(http, redis=redis, retry_interval_seconds=0.01)
    client.charge(usage_payload())
    http.post_script = [FakeResponse(200, {"duplicate": False})]

    async def scenario():
        await client.start_retrier()
        for _ in range(200):
            if not queued(redis):
                break
            await asyncio.sleep(0.01)
        await client.stop_retrier()

    asyncio.run(scenario())

    assert queued(redis) == []
    assert http.posts[-1]["json"]["idempotencyKey"] == KEY
