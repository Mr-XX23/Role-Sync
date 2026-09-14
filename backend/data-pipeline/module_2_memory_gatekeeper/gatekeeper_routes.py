"""Gatekeeper visibility and review endpoints.

The gatekeeper decides what never enters the knowledge base, so those decisions
need to be inspectable and reversible: previously they were written to an
in-process list with no way to read them, and quarantined documents could not be
reviewed or replayed.
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from billing.preflight import require_credits
from module_1_document_processing.connector_privacy import visible_to
from module_1_document_processing.identity import bind_identity
from module_1_document_processing.workspace_access import (
    WorkspaceAccess,
    require_workspace_member,
    require_writer,
)
from module_1_document_processing.pipeline import ingestion_guards as guards
from module_1_document_processing.pipeline.durable_queue import ingest_queue
from module_2_memory_gatekeeper.gatekeeper_store import gatekeeper_store
from module_2_memory_gatekeeper.policy import load_policy
from module_2_memory_gatekeeper.semantic_scorer import semantic_scorer

router = APIRouter(tags=["Gatekeeper"], dependencies=[Depends(bind_identity)])


class ReleaseResponse(BaseModel):
    status: str
    doc_id: str
    message: str
    # True when the document was put back on the ingestion queue. False only for
    # holds recorded before replay existed, which carry nothing to replay.
    requeued: bool = False


@router.get("/gatekeeper/policy")
def get_gatekeeper_policy(access: WorkspaceAccess = Depends(require_workspace_member)):
    """The active policy, including whether the semantic scorer is enforced."""
    policy = load_policy()
    return {
        "status": "success",
        "policy": policy.describe(),
        "semantic_scorer_available": semantic_scorer.available(),
        "mode": "enforcing" if policy.semantic_enforced else "log-only",
    }


@router.get("/gatekeeper/decisions/{doc_id}")
def get_decisions(doc_id: str, access: WorkspaceAccess = Depends(require_workspace_member)):
    """Audit trail for one document: what was decided, why, and under which policy."""
    decisions = gatekeeper_store.decisions_for_doc(doc_id, tenant_id=access.workspace_id)
    return {"status": "success", "doc_id": doc_id, "count": len(decisions), "decisions": decisions}


@router.get("/gatekeeper/holds")
def list_holds(
    kind: Optional[str] = Query(default=None, description="REJECTED or QUARANTINED"),
    limit: int = Query(default=100, ge=1, le=500),
    access: WorkspaceAccess = Depends(require_workspace_member),
):
    """Documents the gatekeeper kept out, with the reason and a content preview."""
    if kind and kind.upper() not in ("REJECTED", "QUARANTINED"):
        raise HTTPException(status_code=400, detail="kind must be REJECTED or QUARANTINED.")

    holds = gatekeeper_store.list_holds(access.workspace_id, kind=(kind or ""), limit=limit)
    # A held document synced from a rep's apps is theirs alone, like everything else they sync.
    holds = [h for h in holds if visible_to({"source": h.source, "user_id": h.user_id}, access.user_id)]
    return {
        "status": "success",
        "count": len(holds),
        "holds": [
            {
                "doc_id": h.doc_id,
                "kind": h.kind,
                "source": h.source,
                "category": h.category,
                "reason": h.reason,
                "preview": h.preview,
                "char_count": h.char_count,
                "semantic_score": h.semantic_score,
                "status": h.status,
                "created_at": h.created_at.isoformat() if h.created_at else None,
                "expires_at": h.expires_at.isoformat() if h.expires_at else None,
            }
            for h in holds
        ],
    }


@router.post("/gatekeeper/holds/{doc_id}/release", response_model=ReleaseResponse)
def release_hold(doc_id: str, access: WorkspaceAccess = Depends(require_workspace_member)):
    """Release a held document after review and put it back on the ingestion queue.

    This used to change the hold's status and nothing else, leaving the person to
    re-upload the file - the architecture's "replay after human review" loop ended
    in a dead end. The replayed job skips the gatekeeper (evaluating it again would
    only reject it again) and that bypass is written to the audit trail.
    """
    require_writer(access)

    hold = gatekeeper_store.get_hold(doc_id, tenant_id=access.workspace_id)
    # Anything not still HELD (already released) is not releasable, and must read
    # the same as absent rather than reporting a second success.
    if not hold or hold.status != "HELD" or not visible_to({"source": hold.source, "user_id": hold.user_id}, access.user_id):
        raise HTTPException(status_code=404, detail="No held document with that id.")

    replay = hold.replay if isinstance(hold.replay, dict) else None
    can_replay = bool(replay and replay.get("kind") and isinstance(replay.get("payload"), dict))

    # Checked before releasing: refusing afterwards would leave a released hold
    # that was never requeued, and nothing to retry the release from.
    if can_replay and ingest_queue.is_overloaded():
        raise HTTPException(
            status_code=503,
            detail=guards.QUEUE_FULL_MESSAGE,
            headers={"Retry-After": "120"},
        )
    # The replay parses, classifies and embeds the document again - paid work, refused with 402
    # (before releasing, for the same reason) when the workspace may not spend.
    if can_replay:
        require_credits(access.workspace_id, access.user_id)

    # Release by the canonical id the hold is stored under, not the caller's form.
    if not gatekeeper_store.release(hold.doc_id):
        raise HTTPException(status_code=409, detail="That document could not be released.")

    if not can_replay:
        return ReleaseResponse(
            status="success",
            doc_id=doc_id,
            message=(
                "Released. This document was held before automatic replay existed, "
                "so re-upload or re-index it to add it to your Knowledge Vault."
            ),
            requeued=False,
        )

    ingest_queue.enqueue(replay["kind"], {**replay["payload"], "skip_gatekeeper": True})
    return ReleaseResponse(
        status="success",
        doc_id=doc_id,
        message="Released and queued for ingestion. It will appear in your Knowledge Vault shortly.",
        requeued=True,
    )


@router.post("/gatekeeper/holds/purge-expired")
def purge_expired(access: WorkspaceAccess = Depends(require_workspace_member)):
    """Delete holds past their TTL."""
    require_writer(access)
    removed = gatekeeper_store.purge_expired()
    return {"status": "success", "removed": removed, "message": f"Purged {removed} expired hold(s)."}
