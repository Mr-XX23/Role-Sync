"""Credits through the real API, runner and orchestrator: what a run uses (every model step and connector
action) is charged to the session's workspace, rep and session, and once billing refuses the workspace,
nothing more starts. billing-service, the model, Composio and workspace-service are doubles; Postgres and
Redis are real."""

from __future__ import annotations

import asyncio
from typing import Any
from uuid import UUID

import httpx
import pytest
from pydantic import SecretStr

from app.config import API_PREFIX
from app.container import build_container
from app.core.enums import SessionStatus
from app.main import create_app
from app.models.types import Completion, Message, Role, StreamDone, TextDelta, ToolCall, Usage
from tests.fake_billing import BILLING_URL, FakeBillingService
from tests.integration.conftest import all_events
from tests.support import FakeConnector, make_token

pytestmark = pytest.mark.integration


class EmailReadingBrain:
    """Searches the rep's email for the request, then answers; every step reports its usage."""

    name = "gemini"

    def __init__(self) -> None:
        self.tasks: list[Any] = []

    async def stream(self, task: Any, models: Any):
        self.tasks.append(task)
        if task.messages[-1].role is Role.USER:
            text, calls = "Checking your email.", (ToolCall(id="call_1", name="search_emails", arguments={"query": "from:acme.test"}),)
        else:
            text, calls = "Acme hasn't emailed you.", ()
        yield TextDelta(text)
        message = Message(role=Role.ASSISTANT, content=text, tool_calls=calls)
        usage = Usage(input_tokens=18_000, output_tokens=600, cached_input_tokens=12_000)
        yield StreamDone(Completion(message=message, provider=self.name, model=models[0], usage=usage))


async def test_a_run_is_charged_to_its_workspace_and_a_refused_workspace_starts_nothing(
    settings, clean, workspace_service, rsa_keys, tenant_id, user_id
):
    billing = FakeBillingService()
    workspace = workspace_service.transport()
    http = httpx.AsyncClient(
        transport=httpx.MockTransport(
            lambda request: billing.handler(request) if f"http://{request.url.host}" == BILLING_URL else workspace.handler(request)
        )
    )
    enabled = settings.model_copy(
        update={"billing_enabled": True, "billing_service_url": BILLING_URL, "internal_service_token": SecretStr("internal-test-token")}
    )
    composio = FakeConnector(responses={"GMAIL_FETCH_EMAILS": {"messages": []}})
    container = await build_container(enabled, http_client=http, providers={"gemini": EmailReadingBrain()}, connector=composio)
    headers = {"Cookie": f"access_token={make_token(rsa_keys, user_id)}", "X-Tenant-Id": str(tenant_id)}
    app = create_app(enabled)
    app.state.container = container
    # The workspace is allowed to start, and this run's charges take its balance below zero.
    billing.balance_after_charge = -0.75
    try:
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://engine.test") as client:
            started = await client.post(f"{API_PREFIX}/chat", headers=headers, json={"message": "Did Acme email me?"})
            assert started.status_code == 202, started.text
            session_id = UUID(started.json()["session_id"])
            await _wait_for_status(container, session_id, SessionStatus.DONE)
            await container.billing.flush()

            # Both planning steps and the Gmail search, each once, to the session's workspace, rep and session.
            assert len(composio.executions) == 1
            charges = billing.charges()
            assert sorted(body["operation"] for body in charges) == ["agent.connector_action", "agent.model_call", "agent.model_call"]
            assert {(body["workspaceId"], body["userId"], body["reference"]) for body in charges} == {
                (str(tenant_id), str(user_id), str(session_id))
            }
            [step, _] = billing.charges("agent.model_call")
            assert step["items"] == [
                {"type": "TOKENS", "model": "gemini-3.5-flash", "inputTokens": 18_000, "cachedInputTokens": 12_000, "outputTokens": 600}
            ]
            assert all(request.headers["X-Internal-Token"] == "internal-test-token" for request in billing.requests)

            # The run finished though it went below zero; now billing refuses the workspace, and the check right
            # after isn't answered from the few-second cache (the charges reported the balance spent), so
            # neither a new request nor a follow-up starts anything.
            billing.refuse(tenant_id)
            events_before = len(await all_events(container, session_id))
            turn_before = (await container.sessions.get(session_id)).turn
            new = await client.post(f"{API_PREFIX}/chat", headers=headers, json={"message": "Draft a follow-up"})
            follow_up = await client.post(
                f"{API_PREFIX}/chat", headers=headers, json={"message": "Draft a follow-up", "session_id": str(session_id)}
            )
            for refused in (new, follow_up):
                assert refused.status_code == 402
                assert refused.json()["detail"]["code"] == "OUT_OF_CREDITS"

        [session] = await container.sessions.list_for_user(tenant_id=tenant_id, user_id=user_id, limit=10)
        assert (session.id, session.status, session.turn) == (session_id, SessionStatus.DONE, turn_before)  # no new turn claimed
        assert len(await all_events(container, session_id)) == events_before  # nothing added to its event stream
        assert not container.runner._tasks and not await container.leases.is_held(session_id)
        assert len(billing.charges()) == 3 and billing.requests[-1].method == "GET"  # only the refused checks since
    finally:
        await container.aclose()
        await http.aclose()


async def _wait_for_status(container, session_id: UUID, status: SessionStatus, timeout: float = 10.0) -> None:
    deadline = asyncio.get_running_loop().time() + timeout
    while asyncio.get_running_loop().time() < deadline:
        row = await container.sessions.get(session_id)
        if row is not None and row.status == status and not container.runner._tasks:
            return
        await asyncio.sleep(0.05)
    raise AssertionError(f"session {session_id} never settled as {status}")
