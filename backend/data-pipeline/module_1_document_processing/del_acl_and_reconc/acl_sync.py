from typing import Any
from module_1_document_processing.composio_connector.events.canonical_event import CanonicalEvent
from module_1_document_processing.connector_privacy import chunk_acl, document_id
from module_1_document_processing.pipeline.canonical_store import CanonicalStore
from module_3_batch_ingestion_vector.vector_store import VectorStore

class ACLSyncService:
    """ACL Sync Service propagating real-time permission updates to VectorStore security tags."""

    def __init__(
        self,
        canonical_store: CanonicalStore | None = None,
        vector_store: VectorStore | None = None,
    ) -> None:
        self.canonical_store = canonical_store or CanonicalStore()
        self.vector_store = vector_store or VectorStore()

    def process_acl_change(self, event: CanonicalEvent) -> bool:
        doc_id = document_id(event.tenant_id, event.source, event.user_id, event.external_id)
        new_acl = list(event.acl)
        print(f"[ACLSyncService] Processing ACL change for doc_id={doc_id}: new_acl={new_acl}")

        # 1. Update CanonicalStore ACL snapshot: the provider's permissions, which reconciliation compares with
        self.canonical_store.update_acl(doc_id=doc_id, new_acl=new_acl)

        # 2. Patch vector security tags in VectorStore: the provider's permissions plus the rep the document
        # belongs to, never the whole workspace. Without the rep's entry they could no longer find it.
        self.vector_store.update_acl_for_doc_id(doc_id=doc_id, new_acl=chunk_acl(event.source, event.user_id, new_acl))

        print(f"[ACLSyncService] Patched acl[] array in MongoDB VectorStore for doc_id={doc_id}")
        print(f"[ACLSyncService] Successfully patched ACLs for doc_id={doc_id}")
        return True
