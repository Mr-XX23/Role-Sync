"""Every paid provider call records what it cost: the gatekeeper's scorer, the classifier, LlamaParse and
embeddings. Provider HTTP is faked; nothing leaves the process."""
import json
from types import SimpleNamespace

import pytest
import requests

from billing.metering import UNIT_LLAMAPARSE_PAGE, estimate_tokens, usage_scope
from module_1_document_processing.classification.sales_classifier import SalesClassifier
from module_1_document_processing.composio_connector.events.canonical_event import CanonicalEvent, EventType
from module_1_document_processing.parsing.llama_parser import LlamaParserService
from module_1_document_processing.parsing.parser_service import ParserService
from module_2_memory_gatekeeper import semantic_scorer as scorer_module
from module_2_memory_gatekeeper.policy import DEFAULT_SEMANTIC_MODEL
from module_2_memory_gatekeeper.semantic_scorer import SemanticScorer
from module_3_batch_ingestion_vector import embedding_worker as embedding_module
from module_3_batch_ingestion_vector.chunker import TextNode
from module_3_batch_ingestion_vector.embedding_worker import EmbeddingFailed, EmbeddingWorker
from tests.test_gatekeeper_policy_and_store import make_doc, make_policy


class FakeResponse:
    def __init__(self, status_code=200, body=None):
        self.status_code = status_code
        self._body = body
        self.text = json.dumps(body) if body is not None else ""
        self.headers = {}

    def json(self):
        if self._body is None:
            raise ValueError("no json")
        return self._body


class FakeLlamaParse:
    """LlamaParse's client as the service builds it: one Document per page (split_by_page)."""

    split_by_page = True
    page_separator = None

    def __init__(self, pages):
        self.pages = pages
        self.calls = 0

    def load_data(self, path):
        self.calls += 1
        if isinstance(self.pages, Exception):
            raise self.pages
        return [SimpleNamespace(text=text, metadata={}) for text in self.pages]


def pdf_event(**metadata):
    return CanonicalEvent(
        event_id="evt_1", event_type=EventType.CREATE, source="USER_UPLOAD", tenant_id="t1", user_id="u1",
        external_id="doc_1", raw_ref={}, acl=["user:u1"],
        metadata={"name": "pricing.pdf", "mime_type": "application/pdf", **metadata},
    )


# ---- gatekeeper scorer ------------------------------------------------------
def test_the_scorer_records_gemini_tokens_with_thinking_as_output(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    reply = {
        "candidates": [{"content": {"parts": [{"text": '{"score": 0.9, "reason": "pricing tiers"}'}]}}],
        "usageMetadata": {"promptTokenCount": 850, "candidatesTokenCount": 20, "thoughtsTokenCount": 30},
    }
    monkeypatch.setattr(scorer_module, "requests", SimpleNamespace(post=lambda *a, **k: FakeResponse(200, reply)))

    with usage_scope() as usage:
        score = SemanticScorer(policy=make_policy()).score(make_doc())

    assert score.ok
    assert usage.tokens(DEFAULT_SEMANTIC_MODEL) == (850, 0, 50)


def test_a_scorer_call_that_failed_records_nothing(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    monkeypatch.setattr(scorer_module, "requests", SimpleNamespace(post=lambda *a, **k: FakeResponse(503, {"error": "x"})))

    with usage_scope() as usage:
        SemanticScorer(policy=make_policy()).score(make_doc())

    assert usage.is_empty()


# ---- classifier -------------------------------------------------------------
GOOD = {
    "category": "PRICING_PACKAGING", "target_competitor": None, "target_industry": None,
    "sales_summary": "Enterprise pricing tiers.", "sales_tags": ["pricing"], "confidence_score": 0.9,
}


def test_the_classifier_records_every_answered_request_against_the_model_that_served_it(monkeypatch):
    monkeypatch.setenv("OPEN_ROUTER_API", "sk-or-test")
    monkeypatch.delenv("OPENROUTER_MODEL", raising=False)
    monkeypatch.delenv("OPENROUTER_FALLBACK_MODELS", raising=False)
    replies = iter([
        # Answered but unusable: the tokens were still spent.
        FakeResponse(200, {"model": "dots-studio/dots-3-note-preview:free", "usage": {"prompt_tokens": 1000, "completion_tokens": 30},
                           "choices": [{"message": {"content": "I think this is pricing"}, "finish_reason": "stop"}]}),
        FakeResponse(200, {"model": "nvidia/nemotron-3-super-120b-a12b:free", "usage": {"prompt_tokens": 1000, "completion_tokens": 90},
                           "choices": [{"message": {"content": json.dumps(GOOD)}, "finish_reason": "stop"}]}),
    ])
    monkeypatch.setattr(requests, "post", lambda *a, **k: next(replies))

    with usage_scope() as usage:
        result = SalesClassifier().classify(filename="pricing.pdf", text_content="Enterprise tier pricing and discounts.")

    assert result.category == "PRICING_PACKAGING"
    assert usage.tokens("dots-studio/dots-3-note-preview:free") == (1000, 0, 30)
    assert usage.tokens("nvidia/nemotron-3-super-120b-a12b:free") == (1000, 0, 90)


def test_the_placeholder_classification_calls_no_model_and_costs_nothing(monkeypatch):
    monkeypatch.setenv("OPEN_ROUTER_API", "sk-or-test")

    def no_calls(*args, **kwargs):
        raise AssertionError("the preliminary label must not call a model")

    monkeypatch.setattr(requests, "post", no_calls)

    with usage_scope() as usage:
        SalesClassifier().classify_preliminary(filename="pricing.pdf")

    assert usage.is_empty()


# ---- LlamaParse ---------------------------------------------------------------
def test_llamaparse_records_every_page_it_returned():
    service = LlamaParserService()
    service.parser = FakeLlamaParse(["Pricing", "", "Terms"])

    with usage_scope() as usage:
        parsed = service.parse(pdf_event(), raw_bytes=b"%PDF-1.7 three pages")

    assert parsed.parser_used == "llama_parse"
    assert usage.units(UNIT_LLAMAPARSE_PAGE) == 3


def test_attachments_parsed_by_llamaparse_record_their_pages():
    service = LlamaParserService()
    service.parser = FakeLlamaParse(["Slide 1", "Slide 2"])

    with usage_scope() as usage:
        text, parser_used, status = service.parse_attachment_bytes("deck.pdf", "application/pdf", b"%PDF-1.7 deck")

    assert (parser_used, status) == ("llama_parse", "SUCCESS")
    assert usage.units(UNIT_LLAMAPARSE_PAGE) == 2


def test_a_failed_llamaparse_call_records_no_pages():
    service = LlamaParserService()
    service.parser = FakeLlamaParse(RuntimeError("LlamaParse returned 500"))

    with usage_scope() as usage:
        service.parse(pdf_event(text_content="Pricing tiers supplied by the connector."), raw_bytes=b"%PDF-1.7")

    assert usage.units(UNIT_LLAMAPARSE_PAGE) == 0


@pytest.mark.parametrize("name, mime", [("notes.md", "text/markdown"), ("prices.csv", "text/csv"), ("page.txt", "text/plain")])
def test_text_formats_parse_locally_and_record_no_pages(name, mime):
    service = ParserService()
    service.llama_parser.parser = FakeLlamaParse(["never used"])
    event = pdf_event(name=name, mime_type=mime)

    with usage_scope() as usage:
        parsed = service.parse_event(event, raw_bytes=b"# Pricing\nEnterprise: 49 per seat")

    assert parsed.parser_used == "local_text"
    assert service.llama_parser.parser.calls == 0
    assert usage.is_empty()


# ---- embeddings ---------------------------------------------------------------
def nodes(*texts):
    return [
        TextNode(chunk_id=f"c{i}", doc_id="d", tenant_id="t", user_id="u", source="USER_UPLOAD", external_id="d",
                 text=text, chunk_hash=f"h{i}", acl=[], chunk_index=i, total_chunks=len(texts))
        for i, text in enumerate(texts)
    ]


@pytest.fixture
def gemini_embeddings(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    monkeypatch.setenv("EMBEDDING_MODEL", "gemini-embedding-2")
    monkeypatch.setenv("EMBEDDING_DIMENSIONS", "4")
    state = {"status": 200}

    def post(url, headers=None, json=None, timeout=None):
        if state["status"] != 200:
            return FakeResponse(state["status"], {"error": "bad request"})
        return FakeResponse(200, {"embeddings": [{"values": [1.0, 0.0, 0.0, 0.0]} for _ in json["requests"]]})

    monkeypatch.setattr(embedding_module, "requests", SimpleNamespace(post=post))
    return state


def test_real_embeddings_record_tokens_estimated_from_the_characters_sent(gemini_embeddings):
    texts = ("Enterprise tier pricing", "Renewal terms and discount bands for multi-year deals")

    with usage_scope() as usage:
        embedded = EmbeddingWorker().generate_embeddings(nodes(*texts))

    assert all(not chunk.is_fallback for chunk in embedded)
    assert usage.tokens("gemini-embedding-2") == (estimate_tokens(sum(len(t) for t in texts)), 0, 0)


def test_a_search_query_embedding_is_recorded(gemini_embeddings):
    with usage_scope() as usage:
        assert EmbeddingWorker().embed_query("who wins against Globex on price?") is not None

    assert usage.tokens("gemini-embedding-2") == (estimate_tokens(len("who wins against Globex on price?")), 0, 0)
    assert "query_embedding" in usage.purposes()


def test_pseudo_vectors_and_failed_embeddings_are_not_charged(monkeypatch, gemini_embeddings):
    gemini_embeddings["status"] = 400
    with usage_scope() as failed:
        with pytest.raises(EmbeddingFailed):
            EmbeddingWorker().generate_embeddings(nodes("Pricing"))
    assert failed.is_empty()

    monkeypatch.setenv("GEMINI_API_KEY", "")
    with usage_scope() as fallback:
        embedded = EmbeddingWorker().generate_embeddings(nodes("Pricing"))
    assert embedded[0].is_fallback and fallback.is_empty()
