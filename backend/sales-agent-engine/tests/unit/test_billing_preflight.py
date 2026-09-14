"""Credits before paid work starts: a workspace billing refuses gets 402 with a message for the rep, and
nothing is started (no run, lease, event stream, budget count or model call). Billing being down never
stops the rep. The API runs over ASGI against a container double; billing is the fake service."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from uuid import uuid4

import httpx
import pytest

from app.api.deps import get_tenant
from app.config import API_PREFIX
from app.core.context import Principal, TenantContext
from app.core.enums import SessionStatus, SkillCategory
from app.main import create_app
from app.skills.model import ParsedSkill
from tests.fake_billing import FakeBillingService

WORKSPACE, USER = uuid4(), uuid4()

OUT_OF_CREDITS = {
    "code": "OUT_OF_CREDITS",
    "message": "Your workspace is out of credits. Buy more credits to keep using the assistant.",
}
SUSPENDED = {"code": "CREDITS_SUSPENDED", "message": "Credits for this workspace are suspended. Contact support."}


class Recorder:
    """Records every call made to it; answers with ``returns``."""

    def __init__(self, returns: Any = None) -> None:
        self.calls: list[tuple[tuple, dict]] = []
        self.returns = returns

    async def __call__(self, *args, **kwargs):
        self.calls.append((args, kwargs))
        return self.returns


def _container(settings, billing: FakeBillingService) -> SimpleNamespace:
    session = SimpleNamespace(id=uuid4(), status=SessionStatus.DONE)
    draft = ParsedSkill(
        name="Renewal risk check", description="Use when a renewal is due.", instructions="1. Check.", category=SkillCategory.PIPELINE, tools=()
    )
    return SimpleNamespace(
        settings=settings,
        billing=billing.client(),
        runner=SimpleNamespace(start_new=Recorder(session), continue_session=Recorder(session)),
        sessions=SimpleNamespace(count_running=Recorder(0), get_owned=Recorder(session)),
        budgets=SimpleNamespace(admit_turn=Recorder()),
        skills=SimpleNamespace(draft=Recorder(draft), pickable=Recorder()),
        admin=None,  # no Super Admin Console overrides
    )


def _client(container: SimpleNamespace) -> httpx.AsyncClient:
    app = create_app(container.settings)
    app.state.container = container
    app.dependency_overrides[get_tenant] = lambda: TenantContext(tenant_id=WORKSPACE, principal=Principal(user_id=USER))
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://engine.test")


def _nothing_started(container: SimpleNamespace) -> bool:
    return not (
        container.runner.start_new.calls
        or container.runner.continue_session.calls
        or container.sessions.count_running.calls
        or container.sessions.get_owned.calls
        or container.budgets.admit_turn.calls
    )


@pytest.mark.parametrize(("code", "detail"), [("OUT_OF_CREDITS", OUT_OF_CREDITS), ("CREDITS_SUSPENDED", SUSPENDED)])
async def test_a_refused_workspace_gets_402_and_no_turn_is_started(settings, code, detail):
    billing = FakeBillingService()
    billing.refuse(WORKSPACE, code)
    container = _container(settings, billing)

    async with _client(container) as client:
        new = await client.post(f"{API_PREFIX}/chat", json={"message": "Research Acme"})
        follow_up = await client.post(f"{API_PREFIX}/chat", json={"message": "And their CFO?", "session_id": str(uuid4())})

    for response in (new, follow_up):
        assert response.status_code == 402
        assert response.json() == {"detail": detail}
    assert _nothing_started(container)  # no run, lease or event stream; the rate budget isn't used up either
    assert [request.url.params["userId"] for request in billing.requests] == [str(USER), str(USER)]


async def test_a_workspace_with_credits_starts_its_turn(settings):
    billing = FakeBillingService()
    container = _container(settings, billing)

    async with _client(container) as client:
        response = await client.post(f"{API_PREFIX}/chat", json={"message": "Research Acme"})

    assert response.status_code == 202, response.text
    assert len(container.budgets.admit_turn.calls) == 1 and len(container.runner.start_new.calls) == 1
    assert len(billing.requests) == 1


async def test_a_turn_still_starts_when_billing_is_down(settings):
    container = _container(settings, FakeBillingService(down=True))

    async with _client(container) as client:
        response = await client.post(f"{API_PREFIX}/chat", json={"message": "Research Acme"})

    assert response.status_code == 202, response.text
    assert len(container.runner.start_new.calls) == 1


async def test_an_ai_skill_draft_needs_credits(settings):
    billing = FakeBillingService()
    billing.refuse(WORKSPACE)
    container = _container(settings, billing)
    idea = {"idea": "Check whether customers with renewals coming up might churn"}

    async with _client(container) as client:
        refused = await client.post(f"{API_PREFIX}/skills/draft", json=idea)
        del billing.answers[WORKSPACE]  # credits bought
        drafted = await client.post(f"{API_PREFIX}/skills/draft", json=idea)

    assert refused.status_code == 402 and refused.json() == {"detail": OUT_OF_CREDITS}
    assert drafted.status_code == 200 and drafted.json()["name"] == "Renewal risk check"
    [(args, _)] = container.skills.draft.calls  # the model was asked only once: after credits were there
    assert args == (WORKSPACE, USER, idea["idea"])
