"""Storage for parent chunks - the context a matched child chunk is returned with.

Children are small and embedded, so a query matches them precisely. Their parent
is a wider span of the same document, returned alongside a match so the answer is
built from enough surrounding text. Parents are keyed by document so re-indexing
replaces them wholesale, and every read is scoped to a workspace.

Falls back to memory when Postgres is unavailable, like the other RAG stores.
"""
from __future__ import annotations

from typing import Optional

from module_3_batch_ingestion_vector.chunker import ParentSpan

try:
    from sqlalchemy import delete, func, or_, select

    from rag.database import session_scope
    from rag.models import ParentChunk
    from rag.state import persistence_available

    _RAG_AVAILABLE = True
except Exception:  # pragma: no cover - sqlalchemy / rag package unavailable
    _RAG_AVAILABLE = False


class ParentStore:
    def __init__(self, use_db: Optional[bool] = None) -> None:
        self._memory: dict[str, ParentSpan] = {}
        self._db_override: Optional[bool] = None if use_db is None else (bool(use_db) and _RAG_AVAILABLE)

    @property
    def _db(self) -> bool:
        if self._db_override is not None:
            return self._db_override
        return _RAG_AVAILABLE and persistence_available()

    def replace_for_document(self, doc_id: str, parents: list[ParentSpan]) -> bool:
        """Swap a document's parents in one transaction.

        Replacing rather than upserting matters: if a re-chunk yields fewer
        parents, upserting would leave the old surplus behind, reachable by
        nothing but still taking space and still returned by a stale lookup.
        """
        if self._db:
            try:
                with session_scope() as session:
                    session.execute(delete(ParentChunk).where(ParentChunk.doc_id == doc_id))
                    for span in parents:
                        session.add(
                            ParentChunk(
                                parent_id=span.parent_id,
                                doc_id=span.doc_id,
                                doc_ref_id=span.doc_ref_id,
                                source=span.source,
                                user_id=span.user_id,
                                tenant_id=span.tenant_id,
                                parent_index=span.parent_index,
                                text=span.text,
                            )
                        )
                return True
            except Exception as err:
                print(f"[ParentStore] Could not store parents for {doc_id}: {err}")

        for key in [k for k, v in self._memory.items() if v.doc_id == doc_id]:
            self._memory.pop(key, None)
        for span in parents:
            self._memory[span.parent_id] = span
        return False

    def get_many(self, parent_ids: list[str], tenant_id: str) -> dict[str, ParentSpan]:
        """Parents by id, restricted to one workspace.

        The tenant filter is not redundant: the ids come from search results, and a
        parent must never be readable outside the workspace that owns it.
        """
        wanted = [pid for pid in dict.fromkeys(parent_ids) if pid]
        if not wanted or not tenant_id:
            return {}

        if self._db:
            try:
                with session_scope() as session:
                    rows = session.execute(
                        select(ParentChunk).where(
                            ParentChunk.parent_id.in_(wanted),
                            ParentChunk.tenant_id == tenant_id,
                        )
                    ).scalars().all()
                    return {
                        row.parent_id: ParentSpan(
                            parent_id=row.parent_id,
                            doc_id=row.doc_id,
                            tenant_id=row.tenant_id,
                            parent_index=row.parent_index,
                            text=row.text,
                            doc_ref_id=row.doc_ref_id,
                            source=row.source,
                            user_id=row.user_id,
                        )
                        for row in rows
                    }
            except Exception as err:
                print(f"[ParentStore] Parent lookup failed: {err}")
                return {}

        return {
            pid: self._memory[pid]
            for pid in wanted
            if pid in self._memory and self._memory[pid].tenant_id == tenant_id
        }

    def delete_by_doc_id(self, doc_id: str) -> int:
        """Erase a document's parents, matching either id form exactly.

        Parent text is document content, so erasure that skipped it would leave a
        readable copy of a deleted document behind.
        """
        if not doc_id:
            return 0
        if self._db:
            try:
                with session_scope() as session:
                    result = session.execute(
                        delete(ParentChunk).where(
                            or_(ParentChunk.doc_id == doc_id, ParentChunk.doc_ref_id == doc_id)
                        )
                    )
                    return int(result.rowcount or 0)
            except Exception as err:
                print(f"[ParentStore] Could not delete parents for {doc_id}: {err}")
                return 0

        keys = [k for k, v in self._memory.items() if doc_id in (v.doc_id, v.doc_ref_id)]
        for key in keys:
            self._memory.pop(key, None)
        return len(keys)

    def delete_by_tenant_source_user(self, tenant_id: str, source: str, user_id: str = "") -> int:
        """Purge everything one connector contributed to a workspace."""
        if not tenant_id or not source:
            return 0
        if self._db:
            try:
                with session_scope() as session:
                    stmt = delete(ParentChunk).where(
                        ParentChunk.tenant_id == tenant_id,
                        func.lower(ParentChunk.source) == source.lower(),
                    )
                    if user_id:
                        stmt = stmt.where(ParentChunk.user_id == user_id)
                    return int(session.execute(stmt).rowcount or 0)
            except Exception as err:
                print(f"[ParentStore] Could not purge parents for {tenant_id}/{source}: {err}")
                return 0

        keys = [
            k for k, v in self._memory.items()
            if v.tenant_id == tenant_id
            and v.source.lower() == source.lower()
            and (not user_id or v.user_id == user_id)
        ]
        for key in keys:
            self._memory.pop(key, None)
        return len(keys)


parent_store = ParentStore()
