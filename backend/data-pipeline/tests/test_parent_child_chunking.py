"""Hierarchical parent/child chunking.

One chunk size had to serve two opposing purposes: small chunks match a query
precisely but give a model too little to answer from, large ones carry context but
match loosely. Documents are now split into wide parents and small children.
Children are embedded and searched; a match brings back its parent as context.
"""
import uuid
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from module_1_document_processing import knowledge_vault_routes as kv
from module_1_document_processing import workspace_access
from module_1_document_processing.parsing.parsed_document import ParsedDocument
from module_1_document_processing.workspace_access import MembershipDirectory
from module_3_batch_ingestion_vector import chunk_config as cc
from module_3_batch_ingestion_vector.chunker import HierarchicalChunker, ParentSpan
from module_3_batch_ingestion_vector.ingestion_pipeline import BatchIngestionPipeline
from module_3_batch_ingestion_vector.parent_store import ParentStore

TENANT = "tenant_a"
OTHER = "tenant_b"


@pytest.fixture(autouse=True)
def no_registered_reader(monkeypatch):
    cc.set_config_reader(None)
    monkeypatch.delenv("PARENT_CHUNK_SIZE", raising=False)
    yield
    cc.set_config_reader(None)


def doc(text: str, tenant_id: str = TENANT, doc_id: str = "", source: str = "USER_UPLOAD") -> ParsedDocument:
    doc_id = doc_id or f"{tenant_id}:{source}:doc_1"
    return ParsedDocument(
        doc_id=doc_id, tenant_id=tenant_id, user_id="u1", source=source,
        external_id=doc_id.rsplit(":", 1)[-1], acl=["user:u1"], mime_type="text/plain", text_content=text,
    )


def paragraphs(count: int, words_each: int = 12) -> str:
    return "\n\n".join(
        " ".join(f"p{p:02d}w{w:02d}" for w in range(words_each)) for p in range(count)
    )


# --- the hierarchy ---------------------------------------------------------
def test_children_are_grouped_under_parents():
    parents, children = HierarchicalChunker(chunk_size=120, chunk_overlap=0).chunk_hierarchy(doc(paragraphs(20)))

    assert len(parents) > 1, "a long document should yield several parents"
    assert len(children) > len(parents)
    parent_ids = {p.parent_id for p in parents}
    for child in children:
        assert child.parent_id in parent_ids
        assert child.metadata["parent_id"] == child.parent_id


def test_every_child_comes_from_inside_its_parent():
    parents, children = HierarchicalChunker(chunk_size=120, chunk_overlap=0).chunk_hierarchy(doc(paragraphs(20)))
    by_id = {p.parent_id: p for p in parents}

    for child in children:
        assert child.text in by_id[child.parent_id].text


def test_parents_cover_the_document_without_overlapping():
    text = paragraphs(20)
    parents, _ = HierarchicalChunker(chunk_size=120, chunk_overlap=30).chunk_hierarchy(doc(text))

    assert " ".join(p.text for p in parents).split() == text.split()


def test_children_are_small_and_parents_are_wide():
    parents, children = HierarchicalChunker(chunk_size=120, chunk_overlap=0).chunk_hierarchy(doc(paragraphs(20)))

    assert all(len(c.text) <= 120 for c in children)
    assert max(len(p.text) for p in parents) > 120


def test_overlap_still_spans_parent_boundaries():
    """Overlap runs over the whole child sequence: a sentence straddling two
    parents is still covered."""
    parents, children = HierarchicalChunker(chunk_size=120, chunk_overlap=30).chunk_hierarchy(doc(paragraphs(20)))
    assert len(parents) > 1

    crossings = [(a, b) for a, b in zip(children, children[1:]) if a.parent_id != b.parent_id]
    assert crossings, "expected at least one child pair across a parent boundary"
    for previous, following in crossings:
        assert following.text.split()[0] in previous.text


def test_children_keep_one_linked_sequence_across_parents():
    _, children = HierarchicalChunker(chunk_size=120, chunk_overlap=20).chunk_hierarchy(doc(paragraphs(20)))

    for idx, child in enumerate(children):
        assert child.chunk_index == idx
        assert child.chunk_id.endswith(f"_chunk_{idx}")
    for previous, following in zip(children, children[1:]):
        assert previous.next_chunk_id == following.chunk_id


def test_parents_carry_what_deletion_matches_on():
    parents, _ = HierarchicalChunker(chunk_size=120, chunk_overlap=0).chunk_hierarchy(
        doc(paragraphs(10), doc_id=f"{TENANT}:gdrive:file_9", source="gdrive")
    )

    assert all(p.doc_ref_id == "file_9" and p.source == "gdrive" and p.user_id == "u1" for p in parents)


def test_chunk_document_still_returns_just_the_children():
    chunker = HierarchicalChunker(chunk_size=120, chunk_overlap=0)
    document = doc(paragraphs(10))

    assert [c.text for c in chunker.chunk_document(document)] == [c.text for c in chunker.chunk_hierarchy(document)[1]]


def test_a_short_document_has_a_single_parent():
    parents, children = HierarchicalChunker(chunk_size=200, chunk_overlap=0).chunk_hierarchy(doc("One short note."))

    assert len(parents) == 1
    assert parents[0].text == "One short note."
    assert children[0].parent_id == parents[0].parent_id


def test_empty_text_has_no_parents_or_children():
    assert HierarchicalChunker(chunk_size=100, chunk_overlap=0).chunk_hierarchy(doc("  ")) == ([], [])


# --- parent sizing ----------------------------------------------------------
def test_parent_defaults_to_four_children_wide():
    assert cc.parent_size_for(500) == 2000


def test_parent_size_can_be_configured(monkeypatch):
    monkeypatch.setenv("PARENT_CHUNK_SIZE", "3000")
    assert cc.parent_size_for(500) == 3000


def test_a_parent_is_never_narrower_than_a_child(monkeypatch):
    monkeypatch.setenv("PARENT_CHUNK_SIZE", "50")
    assert cc.parent_size_for(500) == 500


def test_a_parent_is_capped_for_the_model(monkeypatch):
    monkeypatch.setenv("PARENT_CHUNK_SIZE", "999999")
    assert cc.parent_size_for(500) == cc.MAX_PARENT_SIZE


# --- parent storage ---------------------------------------------------------
def span(pid: str, doc_id: str = f"{TENANT}:USER_UPLOAD:doc_1", tenant: str = TENANT, **kw) -> ParentSpan:
    return ParentSpan(parent_id=pid, doc_id=doc_id, tenant_id=tenant, parent_index=0, text=f"text of {pid}",
                      doc_ref_id=kw.get("doc_ref_id", doc_id.rsplit(":", 1)[-1]),
                      source=kw.get("source", "USER_UPLOAD"), user_id=kw.get("user_id", "u1"))


def test_reindexing_replaces_parents_rather_than_accumulating_them():
    """Upserting would leave the surplus from a longer earlier version behind."""
    store = ParentStore(use_db=False)
    store.replace_for_document(f"{TENANT}:USER_UPLOAD:doc_1", [span("p0"), span("p1"), span("p2")])
    store.replace_for_document(f"{TENANT}:USER_UPLOAD:doc_1", [span("p0")])

    assert set(store.get_many(["p0", "p1", "p2"], TENANT)) == {"p0"}


def test_parents_are_only_readable_inside_their_workspace():
    store = ParentStore(use_db=False)
    store.replace_for_document(f"{TENANT}:USER_UPLOAD:doc_1", [span("p0")])

    assert "p0" in store.get_many(["p0"], TENANT)
    assert store.get_many(["p0"], OTHER) == {}
    assert store.get_many(["p0"], "") == {}


def test_deletion_matches_either_id_form():
    store = ParentStore(use_db=False)
    store.replace_for_document(f"{TENANT}:USER_UPLOAD:doc_1", [span("p0")])
    store.replace_for_document(f"{TENANT}:USER_UPLOAD:doc_2", [span("q0", doc_id=f"{TENANT}:USER_UPLOAD:doc_2")])

    assert store.delete_by_doc_id("doc_1") == 1           # the short id the vault uses
    assert store.delete_by_doc_id(f"{TENANT}:USER_UPLOAD:doc_2") == 1
    assert store.get_many(["p0", "q0"], TENANT) == {}


def test_deletion_is_exact_not_a_pattern():
    """An underscore must not act as a wildcard and remove another document."""
    store = ParentStore(use_db=False)
    store.replace_for_document("t:google_calendar:ev_1", [span("a", doc_id="t:google_calendar:ev_1", tenant="t")])
    store.replace_for_document("t:googleXcalendar:ev_1", [span("b", doc_id="t:googleXcalendar:ev_1", tenant="t")])

    store.delete_by_doc_id("t:google_calendar:ev_1")

    assert set(store.get_many(["a", "b"], "t")) == {"b"}


def test_disconnecting_a_connector_purges_its_parents():
    store = ParentStore(use_db=False)
    store.replace_for_document(f"{TENANT}:gdrive:f1", [span("g", doc_id=f"{TENANT}:gdrive:f1", source="gdrive")])
    store.replace_for_document(f"{TENANT}:notion:n1", [span("n", doc_id=f"{TENANT}:notion:n1", source="notion")])

    assert store.delete_by_tenant_source_user(TENANT, "GDRIVE") == 1
    assert set(store.get_many(["g", "n"], TENANT)) == {"n"}


# --- the pipeline writes parents at the right moment ------------------------
class _Delta:
    def __init__(self, unchanged=False):
        self.unchanged = unchanged

    def filter_changed_chunks(self, nodes):
        return ([], nodes) if self.unchanged else (nodes, [])


class _Embedder:
    def __init__(self, fail=False):
        self.fail = fail

    def generate_embeddings(self, nodes):
        if self.fail:
            raise RuntimeError("embedding failed")
        return nodes


class _Writer:
    vector_store = object()

    def write_embedded_chunks(self, chunks):
        return len(chunks)


def build(parents: ParentStore, delta=None, embedder=None) -> BatchIngestionPipeline:
    return BatchIngestionPipeline(
        chunker=HierarchicalChunker(chunk_size=120, chunk_overlap=0),
        delta_checker=delta or _Delta(), embedding_worker=embedder or _Embedder(),
        bulk_writer=_Writer(), parents=parents,
    )


def test_parents_are_stored_once_children_are_written():
    parents = ParentStore(use_db=False)
    document = doc(paragraphs(20))

    build(parents).process_document(document)

    stored = [s for s in parents._memory.values() if s.doc_id == document.doc_id]
    assert len(stored) > 1


def test_a_failed_embedding_leaves_no_orphan_parents():
    """No context rows that no searchable chunk points to."""
    parents = ParentStore(use_db=False)

    with pytest.raises(RuntimeError):
        build(parents, embedder=_Embedder(fail=True)).process_document(doc(paragraphs(20)))

    assert parents._memory == {}


def test_unchanged_content_still_gains_parents():
    """A document indexed before parents existed would otherwise never get them."""
    parents = ParentStore(use_db=False)

    build(parents, delta=_Delta(unchanged=True)).process_document(doc(paragraphs(20)))

    assert parents._memory


def test_a_chunker_without_parents_still_works():
    class _Flat:
        def chunk_document(self, document):
            return HierarchicalChunker(chunk_size=120, chunk_overlap=0).chunk_document(document)

    parents = ParentStore(use_db=False)
    pipeline = BatchIngestionPipeline(
        chunker=_Flat(), delta_checker=_Delta(), embedding_worker=_Embedder(),
        bulk_writer=_Writer(), parents=parents,
    )

    assert pipeline.process_document(doc(paragraphs(5))) > 0
    assert parents._memory == {}


def test_deleting_a_documents_vectors_erases_its_parents(monkeypatch):
    """Parent text is document content: erasure that skipped it leaves a copy."""
    from module_3_batch_ingestion_vector import parent_store as ps_module
    from module_3_batch_ingestion_vector.vector_store import VectorStore

    parents = ParentStore(use_db=False)
    parents.replace_for_document(f"{TENANT}:USER_UPLOAD:doc_1", [span("p0")])
    monkeypatch.setattr(ps_module, "parent_store", parents)

    store = VectorStore()
    monkeypatch.setattr(store, "_collection", None)
    store.delete_by_doc_id("doc_1")

    assert parents.get_many(["p0"], TENANT) == {}


# --- search returns the parent as context -----------------------------------
WORKSPACE = str(uuid.uuid4())
OWNER = str(uuid.uuid4())


def match(vector_id, parent_id, score, text="matched child text"):
    return SimpleNamespace(
        vector_id=vector_id, doc_id=f"{WORKSPACE}:USER_UPLOAD:doc_1", doc_ref_id="doc_1", external_id="doc_1",
        chunk_index=0, text=text, metadata={"parent_id": parent_id, "similarity_score": score, "category": "PRICING"},
    )


@pytest.fixture
def search(monkeypatch):
    parents = ParentStore(use_db=False)
    doc_id = f"{WORKSPACE}:USER_UPLOAD:doc_1"
    parents.replace_for_document(doc_id, [
        span("P1", doc_id=doc_id, tenant=WORKSPACE),
        span("P2", doc_id=doc_id, tenant=WORKSPACE),
    ])
    state = {"matches": [], "asked_limit": None}

    def fake_search(**kwargs):
        state["asked_limit"] = kwargs["limit"]
        return state["matches"]

    monkeypatch.setattr(kv, "parent_store", parents)
    monkeypatch.setattr(kv.query_embedder, "embed_query", lambda q: [0.1] * 8)
    monkeypatch.setattr(kv.vector_store, "search_similarity", fake_search)
    monkeypatch.setattr(
        workspace_access, "directory",
        MembershipDirectory("http://workspace.test", fetch=lambda base, user, t: {OWNER: {WORKSPACE: "OWNER"}}.get(user, {})),
    )
    app = FastAPI()
    app.include_router(kv.router, prefix="/api/v1")
    client = TestClient(app)

    def run(limit=5):
        return client.post(
            "/api/v1/knowledge-vault/search",
            json={"query": "pricing", "limit": limit},
            headers={"X-User-Id": OWNER, "X-Tenant-Id": WORKSPACE},
        ).json()

    state["run"] = run
    return state


def test_a_match_returns_its_parent_as_context(search):
    search["matches"] = [match("c1", "P1", 0.91)]

    result = search["run"]()["results"][0]

    assert result["text"] == "matched child text"
    assert result["context"] == "text of P1"
    assert result["parent_id"] == "P1"


def test_children_of_one_parent_collapse_to_the_best_match(search):
    """The same context twice would waste the model's context window."""
    search["matches"] = [match("c1", "P1", 0.95), match("c2", "P1", 0.80), match("c3", "P2", 0.70)]

    body = search["run"]()

    assert [r["chunk_id"] for r in body["results"]] == ["c1", "c3"]
    assert body["count"] == 2


def test_search_over_fetches_so_collapsing_still_fills_the_page(search):
    search["matches"] = []

    search["run"](limit=5)

    assert search["asked_limit"] == 15


def test_results_stop_at_the_requested_limit(search):
    search["matches"] = [match("c1", "P1", 0.9), match("c2", "P2", 0.8)]

    assert search["run"](limit=1)["count"] == 1


def test_a_document_indexed_before_parents_falls_back_to_the_chunk(search):
    search["matches"] = [match("legacy", None, 0.9, text="old flat chunk")]

    result = search["run"]()["results"][0]

    assert result["parent_id"] is None
    assert result["context"] == "old flat chunk"


def test_another_workspaces_parent_is_never_returned(search, monkeypatch):
    """Parent ids come from search results; the lookup must still be scoped."""
    foreign = ParentStore(use_db=False)
    foreign.replace_for_document("x:USER_UPLOAD:doc_9", [span("P1", doc_id="x:USER_UPLOAD:doc_9", tenant="other-workspace")])
    monkeypatch.setattr(kv, "parent_store", foreign)
    search["matches"] = [match("c1", "P1", 0.9)]

    result = search["run"]()["results"][0]

    assert result["context"] == "matched child text"  # not the foreign parent's text
