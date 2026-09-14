"""Credits for model calls, web searches and connector actions, metered where every such call passes:
the model router, Tavily and the Composio connector. The billing-service is a fake; providers are doubles
or the real provider parsers fed canned vendor responses."""

from __future__ import annotations

import json
from types import SimpleNamespace
from uuid import uuid4

import httpx
import pytest
from google.genai import types
from pydantic import SecretStr

from app.billing.client import BillingClient
from app.billing.metering import MeteredConnector, MeteredWebSearch, UsageMeter, grounded_prompt_unit
from app.billing.scope import usage_scope
from app.container import default_registry
from app.core.context import AgentContext, RunMode
from app.models.providers.gemini_provider import GeminiProvider
from app.models.providers.openrouter_provider import OpenRouterProvider
from app.models.router import ModelRouter, Route, RoutingRules
from app.models.types import (
    Completion,
    Complexity,
    Message,
    ProviderError,
    ProviderUnavailable,
    RateLimited,
    Role,
    StreamDone,
    TaskSpec,
    TextDelta,
    Usage,
)
from app.observability.tracing import NoopTracingClient
from app.platform.composio_client import ConnectorError, ConnectorOutcomeUnknown
from app.platform.web_search import TavilySearch
from app.skills.service import SkillService
from app.tools.adapters import gmail, web
from app.tools.registry import ToolRegistry
from app.tools.types import ToolFailed, ToolInvocation, ToolOutcomeUnknown
from tests.fake_billing import FakeBillingService
from tests.support import FakeConnector

WORKSPACE, USER, SESSION = uuid4(), uuid4(), uuid4()
CTX = AgentContext(tenant_id=WORKSPACE, user_id=USER, session_id=SESSION, mode=RunMode.INTERACTIVE)

RULES = RoutingRules(
    complex=Route("gemini", ("gemini-3.5-flash",)),
    simple=Route("openrouter", ("cheap-a", "cheap-b")),
    failover=Route("openrouter", ("backup-model",)),
    web_grounded=Route("gemini", ("gemini-2.5-flash",)),
)


def _metered(billing: FakeBillingService) -> tuple[UsageMeter, BillingClient]:
    client = billing.client()
    return UsageMeter(client), client


class Brain:
    """A provider double that reports usage like a real one."""

    def __init__(self, name: str, *, usage: Usage = Usage(), text: str = "Sure.", fail: Exception | None = None, after_text: bool = False):
        self.name = name
        self.usage = usage
        self.text = text
        self.fail = fail
        self.after_text = after_text
        self.calls = 0

    async def stream(self, task, models):
        self.calls += 1
        if self.fail is not None and not self.after_text:
            raise self.fail
        yield TextDelta(self.text)
        if self.fail is not None:
            raise self.fail
        message = Message(role=Role.ASSISTANT, content=self.text)
        yield StreamDone(Completion(message=message, provider=self.name, model=models[0], usage=self.usage))


def _by_purpose(billing: FakeBillingService) -> dict[str, dict]:
    return {body["metadata"]["purpose"]: body for body in billing.charges()}


def _tokens(model: str, input_tokens: int, cached: int, output: int) -> dict:
    return {"type": "TOKENS", "model": model, "inputTokens": input_tokens, "cachedInputTokens": cached, "outputTokens": output}


# --------------------------------------------------------------------------- model calls (router)


async def test_every_completed_model_call_is_charged_once_to_the_workspace_in_scope():
    billing = FakeBillingService()
    meter, client = _metered(billing)
    gemini = Brain("gemini", usage=Usage(input_tokens=18_000, output_tokens=950, cached_input_tokens=12_000))
    router = ModelRouter({"gemini": gemini}, RULES, NoopTracingClient(), meter=meter)

    with usage_scope(WORKSPACE, USER, reference=str(SESSION)):
        # The orchestrator stops reading at StreamDone; the call is charged all the same, and only once.
        async for event in router.stream(TaskSpec(purpose="plan", messages=())):
            if isinstance(event, StreamDone):
                break
        await router.complete(TaskSpec(purpose="subagent:research", messages=()))
    await client.flush()

    charges = _by_purpose(billing)
    assert sorted(charges) == ["plan", "subagent:research"] and len(billing.usage_requests()) == 2
    plan = charges["plan"]
    assert plan["idempotencyKey"].startswith("sales-agent-engine:")
    assert {key: value for key, value in plan.items() if key != "idempotencyKey"} == {
        "workspaceId": str(WORKSPACE),
        "userId": str(USER),
        "operation": "agent.model_call",
        "category": "AGENT",
        "reference": str(SESSION),
        "items": [_tokens("gemini-3.5-flash", 18_000, 12_000, 950)],
        "metadata": {"purpose": "plan", "provider": "gemini"},
    }


async def test_gemini_usage_counts_thinking_as_output_and_reports_the_cached_prompt():
    chunks = [
        types.GenerateContentResponse(
            candidates=[types.Candidate(content=types.Content(role="model", parts=[types.Part(text="Thinking it over", thought=True)]))]
        ),
        types.GenerateContentResponse(
            candidates=[types.Candidate(content=types.Content(role="model", parts=[types.Part(text="Here is the plan.")]))],
            usage_metadata=types.GenerateContentResponseUsageMetadata(
                prompt_token_count=18_000, cached_content_token_count=12_000, candidates_token_count=300, thoughts_token_count=650
            ),
        ),
    ]
    billing = FakeBillingService()
    meter, client = _metered(billing)
    router = ModelRouter({"gemini": _gemini(chunks)}, RULES, NoopTracingClient(), meter=meter)

    with usage_scope(WORKSPACE, USER, reference=str(SESSION)):
        completion = await router.complete(TaskSpec(purpose="plan", messages=()))
    await client.flush()

    assert completion.usage == Usage(input_tokens=18_000, output_tokens=950, cached_input_tokens=12_000)
    [charge] = billing.charges()
    assert charge["items"] == [_tokens("gemini-3.5-flash", 18_000, 12_000, 950)]


async def test_openrouter_usage_reports_the_cached_prompt_and_the_model_that_answered():
    body = _sse(
        {"model": "nvidia/nemotron-3.5-lightning:free", "choices": [{"delta": {"content": "Brief."}, "finish_reason": "stop"}]},
        {
            "choices": [],
            "usage": {
                "prompt_tokens": 2_000,
                "completion_tokens": 120,  # includes the reasoning tokens
                "prompt_tokens_details": {"cached_tokens": 1_500},
                "completion_tokens_details": {"reasoning_tokens": 80},
            },
        },
        "[DONE]",
    )
    http = httpx.AsyncClient(transport=httpx.MockTransport(lambda request: httpx.Response(200, content=body)))
    billing = FakeBillingService()
    meter, client = _metered(billing)
    router = ModelRouter({"openrouter": OpenRouterProvider(api_key="k", http=http)}, RULES, NoopTracingClient(), meter=meter)

    with usage_scope(WORKSPACE, USER, reference=str(SESSION)):
        await router.complete(TaskSpec(purpose="summarize-conversation", messages=(), complexity=Complexity.LOW))
    await client.flush()

    [charge] = billing.charges()
    assert charge["items"] == [_tokens("nvidia/nemotron-3.5-lightning:free", 2_000, 1_500, 120)]
    assert charge["metadata"] == {"purpose": "summarize-conversation", "provider": "openrouter"}


async def test_on_failover_attempts_that_used_tokens_are_charged_and_attempts_that_did_not_are_not():
    billing = FakeBillingService()
    meter, client = _metered(billing)
    backup = Brain("openrouter", usage=Usage(input_tokens=17_500, output_tokens=400))

    # 1) Gemini refuses before producing anything: only the answering failover attempt is charged.
    refused = ModelRouter({"gemini": Brain("gemini", fail=RateLimited("429")), "openrouter": backup}, RULES, NoopTracingClient(), meter=meter)
    # 2) Gemini streams part of an answer, then fails: the tokens it reported are charged, marked partial.
    cut_off = ProviderUnavailable("503 mid-answer").with_usage(Usage(input_tokens=18_000, output_tokens=40), "gemini-3.5-flash")
    mid_answer = ModelRouter(
        {"gemini": Brain("gemini", fail=cut_off, after_text=True), "openrouter": backup}, RULES, NoopTracingClient(), meter=meter
    )
    with usage_scope(WORKSPACE, USER, reference=str(SESSION)):
        await refused.complete(TaskSpec(purpose="first", messages=()))
        await mid_answer.complete(TaskSpec(purpose="second", messages=()))
    await client.flush()

    first = [body for body in billing.charges() if body["metadata"]["purpose"] == "first"]
    assert [(body["metadata"]["provider"], body["items"]) for body in first] == [
        ("openrouter", [_tokens("backup-model", 17_500, 0, 400)])
    ]
    second = sorted((body for body in billing.charges() if body["metadata"]["purpose"] == "second"), key=lambda b: b["metadata"]["provider"])
    assert [(body["metadata"], body["items"]) for body in second] == [
        ({"purpose": "second", "provider": "gemini", "partial": True}, [_tokens("gemini-3.5-flash", 18_000, 0, 40)]),
        ({"purpose": "second", "provider": "openrouter"}, [_tokens("backup-model", 17_500, 0, 400)]),
    ]


async def test_a_gemini_answer_spent_entirely_on_thinking_is_charged_though_it_fails_over():
    chunks = [
        types.GenerateContentResponse(
            candidates=[
                types.Candidate(
                    content=types.Content(role="model", parts=[types.Part(text="…", thought=True)]), finish_reason=types.FinishReason.MAX_TOKENS
                )
            ],
            usage_metadata=types.GenerateContentResponseUsageMetadata(prompt_token_count=9_000, thoughts_token_count=3_000),
        )
    ]
    billing = FakeBillingService()
    meter, client = _metered(billing)
    backup = Brain("openrouter", usage=Usage(input_tokens=9_000, output_tokens=200))
    router = ModelRouter({"gemini": _gemini(chunks), "openrouter": backup}, RULES, NoopTracingClient(), meter=meter)

    with usage_scope(WORKSPACE, USER, reference=str(SESSION)):
        completion = await router.complete(TaskSpec(purpose="plan", messages=()))
    await client.flush()

    assert completion.provider == "openrouter"
    partial = next(body for body in billing.charges() if body["metadata"]["provider"] == "gemini")
    assert partial["items"] == [_tokens("gemini-3.5-flash", 9_000, 0, 3_000)] and partial["metadata"]["partial"] is True
    assert len(billing.charges()) == 2


async def test_a_failure_without_reported_usage_or_with_no_fallback_is_handled_without_extra_charges():
    billing = FakeBillingService()
    meter, client = _metered(billing)
    router = ModelRouter({"openrouter": Brain("openrouter", fail=RateLimited("429"))}, RULES, NoopTracingClient(), meter=meter)

    with usage_scope(WORKSPACE, USER), pytest.raises(RateLimited):
        await router.complete(TaskSpec(purpose="summarize-conversation", messages=(), complexity=Complexity.LOW))
    await client.flush()

    assert billing.requests == []
    assert ProviderError("x").with_usage(Usage(), "m").usage is None  # nothing reported: nothing to charge


async def test_model_calls_with_no_workspace_in_scope_are_not_charged():
    billing = FakeBillingService()
    meter, client = _metered(billing)
    router = ModelRouter({"gemini": Brain("gemini", usage=Usage(1_000, 100))}, RULES, NoopTracingClient(), meter=meter)

    await router.complete(TaskSpec(purpose="plan", messages=()))  # e.g. a background job outside any run
    await client.flush()

    assert billing.requests == []


async def test_metering_problems_never_fail_the_model_call():
    class BrokenMeter:
        def model_call(self, *args, **kwargs):
            raise RuntimeError("meter bug")

    router = ModelRouter({"gemini": Brain("gemini", usage=Usage(1_000, 100))}, RULES, NoopTracingClient(), meter=BrokenMeter())
    with usage_scope(WORKSPACE, USER):
        assert (await router.complete(TaskSpec(purpose="plan", messages=()))).message.content == "Sure."


# --------------------------------------------------------------------------- grounded web answers


@pytest.mark.parametrize(
    ("model", "unit"),
    [
        ("gemini-2.5-flash", "GROUNDED_PROMPT_25"),
        ("gemini-2.0-flash-lite", "GROUNDED_PROMPT_25"),
        ("models/gemini-2.5-pro", "GROUNDED_PROMPT_25"),
        ("gemini-3.5-flash", "GROUNDED_PROMPT_3X"),
        ("gemini-3-pro-preview", "GROUNDED_PROMPT_3X"),
    ],
)
def test_a_grounded_prompt_is_priced_by_gemini_generation(model, unit):
    assert grounded_prompt_unit(model) == unit


@pytest.mark.parametrize(("model", "unit"), [("gemini-2.5-flash", "GROUNDED_PROMPT_25"), ("gemini-3.5-flash", "GROUNDED_PROMPT_3X")])
async def test_a_grounded_web_answer_is_charged_as_a_search_with_its_tokens_and_one_grounded_prompt(model, unit):
    billing = FakeBillingService()
    meter, client = _metered(billing)
    rules = RoutingRules(complex=RULES.complex, simple=RULES.simple, failover=RULES.failover, web_grounded=Route("gemini", (model,)))
    grounding = Brain("gemini", usage=Usage(input_tokens=60, output_tokens=180), text="Acme makes billing software.")
    router = ModelRouter({"gemini": grounding}, rules, NoopTracingClient(), meter=meter)
    research = web.WebResearch(router=router, tavily=None, grounding=True)

    with usage_scope(WORKSPACE, USER, reference=str(SESSION)):
        await _invoke(_tool(web.web_tools(research, router), "web_search"), query="What does Acme do?")
    await client.flush()

    [charge] = billing.charges()
    assert (charge["operation"], charge["category"], charge["reference"]) == ("agent.web_answer", "SEARCH", str(SESSION))
    assert charge["items"] == [_tokens(model, 60, 0, 180), {"type": "UNITS", "unit": unit, "quantity": 1}]
    assert charge["metadata"] == {"purpose": "web_search", "provider": "gemini"}


# --------------------------------------------------------------------------- Tavily


async def test_each_tavily_search_is_charged_and_a_failed_one_is_not():
    answers = [httpx.Response(200, json={"results": [{"title": "Acme", "url": "https://acme.test", "content": "Billing software"}]})]

    def tavily_api(request: httpx.Request) -> httpx.Response:
        return answers.pop(0) if answers else httpx.Response(401, text="bad key")

    billing = FakeBillingService()
    meter, client = _metered(billing)
    tavily = MeteredWebSearch(TavilySearch(api_key="tvly-test", http=httpx.AsyncClient(transport=httpx.MockTransport(tavily_api))), meter)
    router = ModelRouter({}, RULES, NoopTracingClient(), meter=meter)
    search = _tool(web.web_tools(web.WebResearch(router=router, tavily=tavily, grounding=False), router), "web_search")

    with usage_scope(WORKSPACE, USER, reference=str(SESSION)):
        output = await _invoke(search, query="Acme")
        with pytest.raises(ToolFailed, match="Tavily 401"):
            await _invoke(search, query="Acme again")
    await client.flush()

    assert [page["url"] for page in output.data["results"]] == ["https://acme.test"]
    [charge] = billing.charges()
    assert (charge["operation"], charge["category"], charge["workspaceId"]) == ("agent.web_search", "SEARCH", str(WORKSPACE))
    assert charge["items"] == [{"type": "UNITS", "unit": "TAVILY_SEARCH", "quantity": 1}]


# --------------------------------------------------------------------------- Composio


async def test_each_composio_action_that_ran_is_charged_whether_it_reads_or_writes():
    billing = FakeBillingService()
    meter, client = _metered(billing)
    composio = FakeConnector(responses={"GMAIL_FETCH_EMAILS": {"messages": []}})
    tools = gmail.gmail_tools(MeteredConnector(composio, meter))
    send = {"to": ["jane@acme.test"], "subject": "Hi", "body": "Hello"}

    with usage_scope(WORKSPACE, USER, reference=str(SESSION)):
        await _invoke(_tool(tools, "search_emails"), query="from:acme.test")  # read (its connection check isn't an action)
        await _invoke(_tool(tools, "send_email"), **send)  # write
        composio.failures["GMAIL_SEND_EMAIL"] = ConnectorError("GMAIL_SEND_EMAIL failed: invalid recipient")
        with pytest.raises(ConnectorError):
            await _invoke(_tool(tools, "send_email"), **send)  # Composio ran it; Gmail said no
        composio.failures["GMAIL_SEND_EMAIL"] = ConnectorOutcomeUnknown("GMAIL_SEND_EMAIL gave no answer: ReadTimeout")
        with pytest.raises(ToolOutcomeUnknown):
            await _invoke(_tool(tools, "send_email"), **send)  # no answer: not charged
    await client.flush()

    assert len(composio.executions) == 4
    charges = billing.charges("agent.connector_action")
    assert [body["metadata"] for body in charges] == [
        {"action": "GMAIL_FETCH_EMAILS", "successful": True},
        {"action": "GMAIL_SEND_EMAIL", "successful": True},
        {"action": "GMAIL_SEND_EMAIL", "successful": False},
    ]
    assert {(body["category"], json.dumps(body["items"]), body["reference"]) for body in charges} == {
        ("CONNECTORS", json.dumps([{"type": "UNITS", "unit": "COMPOSIO_EXECUTION", "quantity": 1}]), str(SESSION))
    }


# --------------------------------------------------------------------------- outside a run, and the wiring


async def test_an_ai_skill_draft_is_charged_to_the_drafting_reps_workspace():
    text = (
        "---\nname: renewal-risk-check\ndescription: Use when a renewal is coming up.\nmetadata:\n  display_name: Renewal risk check\n"
        "  category: PIPELINE\n  tools: []\n---\n# Renewal risk check\n\n1. List warning signs and what to do about each."
    )
    billing = FakeBillingService()
    meter, client = _metered(billing)
    router = ModelRouter({"gemini": Brain("gemini", usage=Usage(2_400, 700), text=text)}, RULES, NoopTracingClient(), meter=meter)
    directory = SimpleNamespace(role_in=_async(lambda user_id, tenant_id: "MEMBER"))
    skills = SkillService(store=None, directory=directory, registry=ToolRegistry(), router=router)

    drafted = await skills.draft(WORKSPACE, USER, "Check whether customers with renewals coming up might churn")  # no scope set here
    await client.flush()

    assert drafted.name == "Renewal risk check"
    [charge] = billing.charges()
    assert (charge["workspaceId"], charge["userId"], charge["reference"]) == (str(WORKSPACE), str(USER), None)
    assert charge["metadata"] == {"purpose": "skill-draft", "provider": "gemini"}
    assert charge["items"] == [_tokens("gemini-3.5-flash", 2_400, 0, 700)]


async def test_the_default_registry_meters_the_real_composio_and_tavily_tools(settings):
    def tavily_api(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"results": [{"title": "Acme", "url": "https://acme.test", "content": "Billing software"}]})

    billing = FakeBillingService()
    meter, client = _metered(billing)
    router = ModelRouter({}, RULES, NoopTracingClient(), meter=meter)
    registry = default_registry(
        settings.model_copy(update={"tavily_api_key": SecretStr("tvly-test")}),
        connector=FakeConnector(responses={"GMAIL_FETCH_EMAILS": {"messages": []}}),
        router=router,
        http=httpx.AsyncClient(transport=httpx.MockTransport(tavily_api)),
        workspaces=None,
        deals=None,
        meter=meter,
    )

    with usage_scope(WORKSPACE, USER, reference=str(SESSION)):
        await _invoke(registry.get("search_emails"), query="from:acme.test")
        await _invoke(registry.get("web_search"), query="Acme")
    await client.flush()

    assert sorted(body["operation"] for body in billing.charges()) == ["agent.connector_action", "agent.web_search"]


# --------------------------------------------------------------------------- helpers


def _tool(definitions, name):
    return next(d for d in definitions if d.name == name)


async def _invoke(definition, **arguments):
    args = definition.input_model.model_validate(arguments)
    if definition.acl is not None:
        await definition.acl(CTX, args)
    return await definition.handler(ToolInvocation(CTX, "orchestrator", "c1", args))


def _async(fn):
    async def call(*args, **kwargs):
        return fn(*args, **kwargs)

    return call


def _gemini(chunks: list[types.GenerateContentResponse]) -> GeminiProvider:
    class Models:
        async def generate_content_stream(self, *, model, contents, config):
            async def stream():
                for chunk in chunks:
                    yield chunk

            return stream()

    provider = GeminiProvider.__new__(GeminiProvider)
    provider._client = SimpleNamespace(aio=SimpleNamespace(models=Models()))
    return provider


def _sse(*chunks: dict | str) -> bytes:
    lines = [": OPENROUTER PROCESSING", ""]
    for chunk in chunks:
        lines += [f"data: {chunk if isinstance(chunk, str) else json.dumps(chunk)}", ""]
    return "\n".join(lines).encode()
