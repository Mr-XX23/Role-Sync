from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional
import hashlib
from module_1_document_processing.parsing.parsed_document import ParsedDocument
from module_3_batch_ingestion_vector.chunk_config import ChunkConfig, parent_size_for, resolve_chunk_config

@dataclass
class TextNode:
    chunk_id: str
    doc_id: str
    tenant_id: str
    user_id: str
    source: str
    external_id: str
    text: str
    chunk_hash: str
    acl: list[str]
    chunk_index: int
    total_chunks: int
    doc_ref_id: str = ""
    prev_chunk_id: Optional[str] = None
    next_chunk_id: Optional[str] = None
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    # The wider span this chunk belongs to, returned as context when it matches.
    parent_id: Optional[str] = None


@dataclass(frozen=True)
class ParentSpan:
    """A wide span of a document that its small, searchable children belong to."""

    parent_id: str
    doc_id: str
    tenant_id: str
    parent_index: int
    text: str
    doc_ref_id: str = ""
    source: str = ""
    user_id: str = ""


class HierarchicalChunker:
    """Splits a document into overlapping text nodes with hash signatures.

    Two defects lived here. ``chunk_overlap`` was accepted, stored and then never
    used, so chunks never actually overlapped - a sentence spanning a boundary was
    split and neither chunk carried the whole thought, while the workspace's
    `overlap` setting appeared to do something. And a paragraph longer than
    ``chunk_size`` became one oversized chunk instead of being split, which
    matters because the embeddings call truncates its input: everything past that
    limit was stored as chunk text but never represented in the vector.

    Settings are resolved per document from the workspace's RAG config unless
    passed explicitly, so every ingestion path chunks the same way.

    It is also now genuinely hierarchical, as the architecture specifies. One
    chunk size used to serve two opposing purposes: small chunks match a query
    precisely but give a model too little to answer from, large ones carry the
    context but match loosely. The document is split into wide parents, and each
    parent into small children. Children are embedded and searched; a matched
    child brings back its parent as context. Overlap is applied across the whole
    child sequence, so a sentence straddling a parent boundary is still covered.
    """

    def __init__(self, chunk_size: Optional[int] = None, chunk_overlap: Optional[int] = None) -> None:
        # Explicit values win; anything left unset is resolved per document, so
        # the connector path honours the same configuration as an upload.
        self._explicit_size = chunk_size
        self._explicit_overlap = chunk_overlap

    def config_for(self, document: ParsedDocument) -> ChunkConfig:
        if self._explicit_size is not None and self._explicit_overlap is not None:
            size, overlap = self._explicit_size, self._explicit_overlap
        else:
            resolved = resolve_chunk_config(document.tenant_id, document.user_id)
            size = self._explicit_size if self._explicit_size is not None else resolved.chunk_size
            overlap = self._explicit_overlap if self._explicit_overlap is not None else resolved.chunk_overlap
        size = max(1, size)
        # Overlap has to stay below the chunk size or the window never advances.
        return ChunkConfig(chunk_size=size, chunk_overlap=max(0, min(overlap, size - 1)))

    # ---- text splitting ---------------------------------------------------
    @staticmethod
    def _split_long(text: str, size: int) -> list[str]:
        """Break a run of text longer than one chunk, preferring word boundaries."""
        pieces: list[str] = []
        remaining = text
        while len(remaining) > size:
            cut = remaining.rfind(" ", 0, size + 1)
            if cut <= 0:  # no break available (e.g. one very long token): hard cut
                cut = size
            pieces.append(remaining[:cut].strip())
            remaining = remaining[cut:].lstrip()
        if remaining:
            pieces.append(remaining)
        return [p for p in pieces if p]

    def _pack(self, text: str, size: int) -> list[str]:
        """Group paragraphs up to `size`, splitting any that exceed it alone."""
        chunks: list[str] = []
        current = ""
        for para in (p.strip() for p in text.split("\n\n")):
            if not para:
                continue
            if len(para) > size:
                # Flush what is held, then split the oversized paragraph rather
                # than emitting a chunk the embedding step would truncate.
                if current:
                    chunks.append(current)
                    current = ""
                chunks.extend(self._split_long(para, size))
                continue
            separator = 2 if current else 0
            if len(current) + separator + len(para) <= size:
                current += ("\n\n" if current else "") + para
            else:
                if current:
                    chunks.append(current)
                current = para
        if current:
            chunks.append(current)
        return chunks

    @staticmethod
    def _apply_overlap(chunks: list[str], overlap: int) -> list[str]:
        """Carry the tail of each chunk into the next so context spans boundaries."""
        if overlap <= 0 or len(chunks) < 2:
            return chunks
        overlapped = [chunks[0]]
        for previous, chunk in zip(chunks, chunks[1:]):
            tail = previous[-overlap:]
            # Begin the carried text at a word boundary so it reads as language
            # instead of starting mid-word.
            space = tail.find(" ")
            if space != -1:
                tail = tail[space + 1:]
            tail = tail.strip()
            overlapped.append(f"{tail} {chunk}" if tail else chunk)
        return overlapped

    def chunk_document(self, document: ParsedDocument) -> list[TextNode]:
        """The searchable children. See chunk_hierarchy for their parents too."""
        return self.chunk_hierarchy(document)[1]

    def chunk_hierarchy(self, document: ParsedDocument) -> tuple[list[ParentSpan], list[TextNode]]:
        text = (document.text_content or "").strip()
        if not text:
            return [], []

        config = self.config_for(document)
        parent_texts = self._pack(text, parent_size_for(config.chunk_size))

        # Children are cut from each parent, remembering which parent owns them,
        # then overlapped as one sequence so context still spans parent edges.
        base_children: list[str] = []
        owner: list[int] = []
        for parent_index, parent_text in enumerate(parent_texts):
            for child in self._pack(parent_text, config.chunk_size):
                base_children.append(child)
                owner.append(parent_index)
        chunks = self._apply_overlap(base_children, config.chunk_overlap)

        parent_ids = [f"{document.doc_id}_parent_{k}" for k in range(len(parent_texts))]
        parents = [
            ParentSpan(
                parent_id=parent_ids[k],
                doc_id=document.doc_id,
                tenant_id=document.tenant_id,
                parent_index=k,
                text=parent_text,
                doc_ref_id=document.external_id or document.doc_id,
                source=document.source or "",
                user_id=document.user_id or "",
            )
            for k, parent_text in enumerate(parent_texts)
        ]

        nodes: list[TextNode] = []
        total = len(chunks)
        doc_ref = document.external_id or document.doc_id

        # Precompute chunk IDs to enable bidirectional linked list chaining
        chunk_ids = [f"{document.doc_id}_chunk_{i}" for i in range(total)]

        for idx, chunk_text in enumerate(chunks):
            chunk_hash = hashlib.md5(chunk_text.encode("utf-8")).hexdigest()
            chunk_id = chunk_ids[idx]
            prev_id = chunk_ids[idx - 1] if idx > 0 else None
            next_id = chunk_ids[idx + 1] if idx < total - 1 else None

            node_metadata = {
                **document.metadata,
                "mime_type": document.mime_type,
                "parser_used": document.parser_used,
                "doc_ref_id": doc_ref,
                "parent_doc_id": doc_ref,
                "chunk_index": idx,
                "total_chunks": total,
                "prev_chunk_id": prev_id,
                "next_chunk_id": next_id,
                "parent_id": parent_ids[owner[idx]],
                "parent_index": owner[idx],
            }

            node = TextNode(
                chunk_id=chunk_id,
                doc_id=document.doc_id,
                tenant_id=document.tenant_id,
                user_id=document.user_id,
                source=document.source,
                external_id=document.external_id,
                doc_ref_id=doc_ref,
                text=chunk_text,
                chunk_hash=chunk_hash,
                acl=list(document.acl),
                chunk_index=idx,
                total_chunks=total,
                prev_chunk_id=prev_id,
                next_chunk_id=next_id,
                metadata=node_metadata,
                parent_id=parent_ids[owner[idx]],
            )
            nodes.append(node)

        print(
            f"[HierarchicalChunker] Chunked doc_id={document.doc_id} into {len(nodes)} child nodes "
            f"under {len(parents)} parent(s) (size={config.chunk_size}, overlap={config.chunk_overlap}, "
            f"doc_ref_id={doc_ref}) with ACL tags: {document.acl}"
        )
        return parents, nodes
