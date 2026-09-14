"""Collecting provider usage while work runs, and the shape it is reported in."""
import asyncio
import json
from types import SimpleNamespace

from billing.charges import idempotency_key
from billing.metering import (
    UNIT_COMPOSIO_EXECUTION,
    UNIT_LLAMAPARSE_PAGE,
    UsageMeter,
    count_llamaparse_pages,
    estimate_tokens,
    execution_scope,
    record_composio_execution,
    record_gemini_usage,
    record_llamaparse_pages,
    record_openrouter_usage,
    record_tokens,
    usage_scope,
)


def test_usage_recorded_outside_a_scope_goes_nowhere():
    record_tokens("gemini-3.5-flash-lite", 100, 10)
    record_llamaparse_pages(3)
    record_composio_execution()

    with usage_scope() as usage, execution_scope() as executions:
        pass

    assert usage.is_empty() and executions.is_empty()


def test_a_scope_collects_its_own_usage_and_can_be_joined():
    with usage_scope() as outer:
        record_tokens("gemini-3.5-flash-lite", 100, 10, purpose="gatekeeper_scorer")
        with usage_scope() as separate:
            record_tokens("gemini-3.5-flash-lite", 1, 1)
        with usage_scope(join=True) as joined:
            record_llamaparse_pages(3)
        with usage_scope(outer):  # continue a meter started earlier
            record_llamaparse_pages(2)

    assert joined is outer
    assert outer.tokens("gemini-3.5-flash-lite") == (100, 0, 10)
    assert outer.units(UNIT_LLAMAPARSE_PAGE) == 5
    assert separate.tokens("gemini-3.5-flash-lite") == (1, 0, 1)


def test_usage_follows_the_work_into_worker_threads():
    async def scenario():
        with usage_scope() as usage:
            await asyncio.to_thread(record_tokens, "gemini-3.5-flash-lite", 7, 3)
            await asyncio.gather(*(asyncio.to_thread(record_llamaparse_pages, 1) for _ in range(5)))
        return usage

    usage = asyncio.run(scenario())

    assert usage.tokens("gemini-3.5-flash-lite") == (7, 0, 3)
    assert usage.units(UNIT_LLAMAPARSE_PAGE) == 5


def test_documents_processed_concurrently_do_not_share_usage():
    async def one_document(pages):
        with usage_scope() as usage:
            await asyncio.sleep(0)
            await asyncio.to_thread(record_llamaparse_pages, pages)
            await asyncio.sleep(0)
        return usage.units(UNIT_LLAMAPARSE_PAGE)

    async def scenario():
        return await asyncio.gather(one_document(1), one_document(2), one_document(3))

    assert asyncio.run(scenario()) == [1, 2, 3]


def test_connector_executions_are_collected_apart_from_document_usage():
    with execution_scope() as executions:
        with usage_scope() as usage:
            record_composio_execution()
            record_composio_execution()
            record_tokens("gemini-embedding-2", 40)

    assert executions.items() == [{"type": "UNITS", "unit": UNIT_COMPOSIO_EXECUTION, "quantity": 2}]
    assert usage.units(UNIT_COMPOSIO_EXECUTION) == 0


def test_items_have_the_contract_shape():
    meter = UsageMeter()
    meter.add_tokens("gemini-3.5-flash-lite", 1200, 80, cached_input_tokens=200)
    meter.add_tokens("gemini-3.5-flash-lite", 300, 20)
    meter.add_units(UNIT_LLAMAPARSE_PAGE, 8)

    assert meter.items() == [
        {"type": "TOKENS", "model": "gemini-3.5-flash-lite", "inputTokens": 1500, "cachedInputTokens": 200, "outputTokens": 100},
        {"type": "UNITS", "unit": "LLAMAPARSE_PAGE", "quantity": 8},
    ]


def test_usage_survives_a_queue_payload_round_trip_and_merges():
    meter = UsageMeter()
    meter.add_tokens("nvidia/nemotron-3-super-120b-a12b:free", 1000, 90, purpose="classifier")
    meter.add_units(UNIT_LLAMAPARSE_PAGE, 3, purpose="llamaparse")

    restored = UsageMeter.from_dict(json.loads(json.dumps(meter.to_dict())))
    restored.merge(meter)

    assert restored.tokens("nvidia/nemotron-3-super-120b-a12b:free") == (2000, 0, 180)
    assert restored.units(UNIT_LLAMAPARSE_PAGE) == 6
    assert restored.purposes()["classifier"]["calls"] == 2


def test_gemini_thinking_tokens_are_output():
    with usage_scope() as usage:
        record_gemini_usage(
            "gemini-3.5-flash-lite",
            {"usageMetadata": {"promptTokenCount": 900, "candidatesTokenCount": 40, "thoughtsTokenCount": 60, "cachedContentTokenCount": 100}},
            purpose="gatekeeper_scorer",
        )

    assert usage.tokens("gemini-3.5-flash-lite") == (900, 100, 100)


def test_openrouter_tokens_are_charged_to_the_model_that_served_the_request():
    body = {
        "model": "nvidia/nemotron-3-super-120b-a12b:free",
        "usage": {"prompt_tokens": 1500, "completion_tokens": 120, "prompt_tokens_details": {"cached_tokens": 100}},
    }

    with usage_scope() as usage:
        record_openrouter_usage(body, "openrouter/free", purpose="classifier")

    assert usage.tokens("nvidia/nemotron-3-super-120b-a12b:free") == (1500, 100, 120)
    assert usage.tokens("openrouter/free") == (0, 0, 0)


def test_a_reply_without_counts_is_estimated_and_marked():
    body = {"choices": [{"message": {"content": "x" * 35}}]}

    with usage_scope() as usage:
        record_openrouter_usage(body, "meta-llama/llama-3.3-70b-instruct:free", purpose="catalog_findability", prompt_chars=700)

    assert usage.tokens("meta-llama/llama-3.3-70b-instruct:free") == (201, 0, 11)
    assert usage.purposes()["catalog_findability"]["estimated"] is True


def test_embedding_tokens_are_estimated_at_three_and_a_half_characters_each():
    assert estimate_tokens(0) == 0
    assert estimate_tokens(7) == 3
    assert estimate_tokens(3500) == 1001


def test_llamaparse_pages_are_the_documents_it_returned():
    one_per_page = SimpleNamespace(split_by_page=True)
    pages = [SimpleNamespace(text="Pricing"), SimpleNamespace(text=""), SimpleNamespace(text="Terms")]
    assert count_llamaparse_pages(one_per_page, pages) == 3  # a blank page is still a parsed page
    assert count_llamaparse_pages(one_per_page, []) == 0

    joined = SimpleNamespace(split_by_page=False, page_separator=None)
    assert count_llamaparse_pages(joined, [SimpleNamespace(text="a\n---\nb\n---\nc")]) == 3


def test_idempotency_keys_are_stable_and_bounded():
    assert idempotency_key("knowledge.search", "", None, "r1") == "knowledge.search:r1"

    long_doc_id = f"{'a' * 36}:gmail:{'b' * 36}:{'m' * 180}"
    key = idempotency_key("document.ingest", long_doc_id, "0123456789abcdef", "index")
    assert len(key) <= 200 and key.startswith("document.ingest:sha256:")
    assert key == idempotency_key("document.ingest", long_doc_id, "0123456789abcdef", "index")
    assert key != idempotency_key("document.ingest", long_doc_id, "0123456789abcdef", "held")
