"""The document classifier's OpenRouter path.

Free models used to fail in ways the code could not see: two of four candidates
were rate-limited, and the other two answered but spent a 400-token budget
reasoning and were cut off mid-JSON - replies the code skipped without a word,
leaving documents to keyword rules that filed a resume as a PRODUCT_SPEC against
"Jira". The classifier now asks openrouter/free for an enforced schema, only from
models that honour it, with reasoning off; logs every rejected reply; and stops at
once when the shared free daily allowance is gone.
"""
import json

import pytest
import requests

from module_1_document_processing.classification.sales_classifier import (
    VALID_SALES_CATEGORIES,
    SalesClassifier,
    classification_response_schema,
)

RESUME = "Rohan Balami - Software Engineer. Java, Python, sprint planning in Jira, AWS."


class FakeResponse:
    def __init__(self, status_code=200, body=None, text=None):
        self.status_code = status_code
        self._body = body
        self.text = text if text is not None else json.dumps(body or {})

    def json(self):
        if self._body is None:
            raise ValueError("no json")
        return self._body


def reply(parsed=None, served="nex-agi/nex-n2.5-pro:free", content=None, finish="stop"):
    if content is None:
        content = json.dumps(parsed)
    return FakeResponse(200, {"model": served, "choices": [{"message": {"content": content}, "finish_reason": finish}]})


GOOD = {
    "category": "GENERAL_RESOURCE", "target_competitor": None, "target_industry": "Technology",
    "sales_summary": "Resume of a software engineer.", "sales_tags": ["resume"], "confidence_score": 0.9,
}


@pytest.fixture
def api(monkeypatch):
    """Scripted OpenRouter responses; records every request body."""
    monkeypatch.setenv("OPEN_ROUTER_API", "sk-or-test")
    monkeypatch.delenv("OPENROUTER_MODEL", raising=False)
    monkeypatch.delenv("OPENROUTER_FALLBACK_MODELS", raising=False)
    state = {"script": [], "calls": []}

    def fake_post(url, headers=None, json=None, timeout=None):
        state["calls"].append({"url": url, "body": json, "timeout": timeout})
        item = state["script"][min(len(state["calls"]) - 1, len(state["script"]) - 1)]
        if isinstance(item, Exception):
            raise item
        return item

    monkeypatch.setattr(requests, "post", fake_post)
    return state


def classify(filename="Rohan Balami 2026 Resume.pdf", text=RESUME):
    return SalesClassifier().classify(filename=filename, mime_type="application/pdf", text_content=text)


# --- what is asked for ------------------------------------------------------
def test_requests_openrouter_free_with_an_enforced_schema(api):
    api["script"] = [reply(GOOD)]

    classify()

    body = api["calls"][0]["body"]
    assert body["model"] == "openrouter/free"
    assert body["response_format"]["type"] == "json_schema"
    assert body["response_format"]["json_schema"]["strict"] is True
    assert body["temperature"] == 0


def test_only_models_that_honour_the_schema_may_serve_it(api):
    """Without this, the router could pick a model that ignores response_format."""
    api["script"] = [reply(GOOD)]

    classify()

    assert api["calls"][0]["body"]["provider"] == {"require_parameters": True}


def test_reasoning_is_off_and_the_answer_has_room(api):
    """Reasoning used to exhaust a 400-token budget before any JSON was written."""
    api["script"] = [reply(GOOD)]

    classify()

    body = api["calls"][0]["body"]
    assert body["reasoning"] == {"enabled": False}
    assert body["max_tokens"] >= 1024


def test_the_schema_allows_exactly_the_known_categories():
    schema = classification_response_schema()["schema"]
    assert set(schema["properties"]["category"]["enum"]) == VALID_SALES_CATEGORIES
    assert schema["additionalProperties"] is False


def test_the_prompt_says_resumes_are_not_sales_material_and_tools_are_not_competitors(api):
    api["script"] = [reply(GOOD)]

    classify()

    system = api["calls"][0]["body"]["messages"][0]["content"]
    assert "resumes" in system.lower()
    assert "NOT a competitor" in system


# --- using the answer -------------------------------------------------------
def test_a_valid_reply_becomes_the_classification(api):
    api["script"] = [reply(GOOD)]

    result = classify()

    assert result.category == "GENERAL_RESOURCE"
    assert result.target_competitor is None
    assert result.target_industry == "Technology"


def test_the_model_that_actually_classified_is_recorded(api):
    """openrouter/free picks a model per request; a bad label is only diagnosable
    if you can see which model produced it."""
    api["script"] = [reply(GOOD, served="dots-studio/dots-3-note-preview:free")]

    result = classify()

    assert result.classifier_used == "openrouter:openrouter/free->dots-studio/dots-3-note-preview:free"


def test_null_like_values_and_out_of_range_confidence_are_normalised(api):
    api["script"] = [reply({**GOOD, "target_competitor": "null", "target_industry": "None", "confidence_score": 7})]

    result = classify()

    assert result.target_competitor is None
    assert result.target_industry is None
    assert result.confidence_score == 1.0


# --- rejecting bad replies, visibly -----------------------------------------
@pytest.mark.parametrize(
    "bad, reason",
    [
        (reply(content=""), "no content"),
        (reply(content='{"category": "GENERAL_RESOURCE", "target_comp', finish="length"), "unusable output"),
        (reply({**GOOD, "category": "RESUME"}), "unknown category"),
        (FakeResponse(200, None, text="<html>oops</html>"), "non-JSON response body"),
    ],
)
def test_an_unusable_reply_is_logged_and_retried(api, capsys, bad, reason):
    api["script"] = [bad, reply(GOOD)]

    result = classify()

    assert result.category == "GENERAL_RESOURCE"
    assert len(api["calls"]) == 2
    assert reason in capsys.readouterr().out  # never silently discarded again


def test_a_timeout_is_retried(api):
    api["script"] = [requests.Timeout("slow"), reply(GOOD)]

    assert classify().classifier_used.startswith("openrouter:")
    assert len(api["calls"]) == 2


def test_attempts_are_bounded_then_keyword_rules_answer(api, monkeypatch):
    monkeypatch.setenv("CLASSIFIER_ATTEMPTS_PER_MODEL", "3")
    api["script"] = [FakeResponse(429, text='{"error":{"message":"Provider returned error"}}')]

    result = classify()

    assert len(api["calls"]) == 3
    assert result.classifier_used == "heuristic_rule_engine"


# --- knowing when to stop ---------------------------------------------------
def test_the_daily_free_limit_stops_immediately(api, capsys):
    """Every free model shares the allowance: retrying only delays the fallback."""
    api["script"] = [FakeResponse(429, text='{"error":{"message":"Rate limit exceeded: free-models-per-day."}}')]

    result = classify()

    assert len(api["calls"]) == 1
    assert result.classifier_used == "heuristic_rule_engine"
    assert "daily limit" in capsys.readouterr().out


@pytest.mark.parametrize("status", [401, 402])
def test_a_rejected_key_stops_immediately(api, status):
    api["script"] = [FakeResponse(status, text='{"error":{"message":"No auth credentials found"}}')]

    assert classify().classifier_used == "heuristic_rule_engine"
    assert len(api["calls"]) == 1


def test_a_model_that_cannot_serve_the_request_moves_on_to_the_fallback(api, monkeypatch):
    monkeypatch.setenv("OPENROUTER_FALLBACK_MODELS", "nex-agi/nex-n2.5-pro:free")
    api["script"] = [
        FakeResponse(404, text='{"error":{"message":"No endpoints found that support the requested parameters"}}'),
        reply(GOOD, served="nex-agi/nex-n2.5-pro:free"),
    ]

    result = classify()

    assert [c["body"]["model"] for c in api["calls"]] == ["openrouter/free", "nex-agi/nex-n2.5-pro:free"]
    assert result.classifier_used == "openrouter:nex-agi/nex-n2.5-pro:free"


def test_fallback_models_are_configurable_and_deduplicated(api, monkeypatch):
    monkeypatch.setenv("OPENROUTER_MODEL", "openrouter/free")
    monkeypatch.setenv("OPENROUTER_FALLBACK_MODELS", " a/one:free , openrouter/free, b/two:free ")
    monkeypatch.setenv("CLASSIFIER_ATTEMPTS_PER_MODEL", "1")
    api["script"] = [FakeResponse(503, text="unavailable")]

    classify()

    assert [c["body"]["model"] for c in api["calls"]] == ["openrouter/free", "a/one:free", "b/two:free"]


def test_without_a_key_no_request_is_made(api, monkeypatch):
    monkeypatch.setenv("OPEN_ROUTER_API", "")
    api["script"] = [reply(GOOD)]

    result = classify()

    assert api["calls"] == []
    assert result.classifier_used == "heuristic_rule_engine"


# --- the preliminary label --------------------------------------------------
def test_the_preliminary_label_never_calls_a_model(api):
    """It used to spend a request classifying a bare filename inside the upload."""
    api["script"] = [reply(GOOD)]

    result = SalesClassifier().classify_preliminary(filename="pricing-2026.pdf")

    assert api["calls"] == []
    assert result.classifier_used == "heuristic_rule_engine"


def test_the_preliminary_label_honours_user_overrides(api):
    result = SalesClassifier().classify_preliminary(
        filename="deck.pdf", user_override_category="battlecard", user_override_competitor="Northwind"
    )

    assert result.category == "BATTLECARD"
    assert result.target_competitor == "Northwind"
    assert result.confidence_score == 1.0
    assert api["calls"] == []


def test_the_preliminary_label_can_use_page_text(api):
    result = SalesClassifier().classify_preliminary(
        filename="page", text_content="SOC 2 Type II report, GDPR data processing addendum and ISO 27001 certificate."
    )

    assert result.category == "SECURITY_COMPLIANCE"
    assert api["calls"] == []
