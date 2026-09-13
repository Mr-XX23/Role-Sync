from module_1_document_processing.parsing.parsed_document import ParsedDocument
from module_3_batch_ingestion_vector.chunker import HierarchicalChunker
from module_3_batch_ingestion_vector.delta_checker import DeltaChecker
from module_3_batch_ingestion_vector.embedding_worker import EmbeddingWorker
from module_3_batch_ingestion_vector.vector_store import VectorStore
from module_3_batch_ingestion_vector.bulk_writer import BulkWriter
from module_3_batch_ingestion_vector.checkpoint_store import CheckpointStore
from module_3_batch_ingestion_vector.parent_store import ParentStore, parent_store

class BatchIngestionPipeline:
    """Facade orchestrating Module 3 Batch Ingestion Pipeline.

    Failures are re-raised rather than absorbed. They used to be pushed to an
    in-memory dead-letter list that nothing ever read - and which was rebuilt per
    document, so it was discarded moments later - leaving a FAILED checkpoint as
    the only trace and no retry of any kind. The ingestion queue is the real dead
    letter queue now: it retries with backoff and keeps what it cannot process.
    """

    def __init__(
        self,
        chunker: HierarchicalChunker | None = None,
        delta_checker: DeltaChecker | None = None,
        embedding_worker: EmbeddingWorker | None = None,
        bulk_writer: BulkWriter | None = None,
        checkpoint_store: CheckpointStore | None = None,
        parents: ParentStore | None = None,
    ) -> None:
        self.chunker = chunker or HierarchicalChunker()
        self.delta_checker = delta_checker or DeltaChecker()
        self.embedding_worker = embedding_worker or EmbeddingWorker()
        self.bulk_writer = bulk_writer or BulkWriter(delta_checker=self.delta_checker)
        self.vector_store = self.bulk_writer.vector_store
        self.checkpoint_store = checkpoint_store or CheckpointStore()
        self.parents = parents or parent_store

    def _store_parents(self, document: ParsedDocument, parent_spans: list) -> None:
        if parent_spans:
            self.parents.replace_for_document(document.doc_id, parent_spans)

    def process_accepted_document(self, document: ParsedDocument) -> int:
        return self.process_document(document)

    def process_document(self, document: ParsedDocument) -> int:
        batch_id = f"batch_{document.doc_id}"
        print(f"[BatchIngestionPipeline] Processing document doc_id={document.doc_id} under batch_id={batch_id}...")

        # 1. Hierarchical Chunking: small children to search, wide parents to answer from.
        hierarchy = getattr(self.chunker, "chunk_hierarchy", None)
        if callable(hierarchy):
            parent_spans, nodes = hierarchy(document)
        else:  # a chunker without parents (tests, custom chunkers)
            parent_spans, nodes = [], self.chunker.chunk_document(document)
        if not nodes:
            print(f"[BatchIngestionPipeline] No text nodes generated for doc_id={document.doc_id}. Skipping.")
            return 0

        # 2. Checkpoint Creation
        self.checkpoint_store.create_checkpoint(batch_id=batch_id, doc_id=document.doc_id, tenant_id=document.tenant_id, chunks_count=len(nodes))
        self.checkpoint_store.update_status(batch_id=batch_id, status="PROCESSING")

        try:
            # 3. Delta Hash Filter
            changed_nodes, unchanged_nodes = self.delta_checker.filter_changed_chunks(nodes)
            if not changed_nodes:
                print(f"[BatchIngestionPipeline] All {len(nodes)} chunks are identical to prior index. Skipping embedding.")
                # Parents are still refreshed: they are cheap to write, and a
                # document indexed before parents existed would otherwise never
                # gain them until its text changed.
                self._store_parents(document, parent_spans)
                self.checkpoint_store.update_status(batch_id=batch_id, status="DONE")
                return 0

            # 4. Batch Embedding Generation
            embedded_chunks = self.embedding_worker.generate_embeddings(changed_nodes)

            # 5. Idempotent Bulk Write to VectorStore & Hash DB Commit
            written_count = self.bulk_writer.write_embedded_chunks(embedded_chunks)

            # 5b. Parents are written only after the children succeed, so a failed
            # embedding never leaves context rows that no searchable chunk points to.
            self._store_parents(document, parent_spans)

            # 6. Mark Checkpoint Done
            self.checkpoint_store.update_status(batch_id=batch_id, status="DONE")
            return written_count

        except Exception as err:
            print(f"[BatchIngestionPipeline] Pipeline failure for doc_id={document.doc_id}: {err}")
            self.checkpoint_store.update_status(batch_id=batch_id, status="FAILED")
            raise
