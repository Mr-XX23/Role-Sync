"""Credit checks before paid work starts.

- User-started paid work (uploads, URL ingests, reindex, reclassify, catalog findability, manual
  connector syncs) calls ``require_credits`` after the caller's identity and workspace membership are
  verified and before any work or storage: a workspace that may not spend gets HTTP 402 with the
  contract's error shape.
- Background work (scheduled syncs, reconciliation sweeps, webhook ingestion) calls
  ``allowed_in_background`` and skips the workspace, with a log line, instead of failing.

Near-free reads (knowledge search, catalog search) are never refused; they are only charged.
When billing-service cannot answer, the check allows the work (see ``billing.client``).
"""
from __future__ import annotations

import asyncio
from typing import Any

from fastapi import HTTPException

from billing.client import CODE_CREDITS_SUSPENDED, CODE_OUT_OF_CREDITS, CreditCheck, canonical_uuid, get_billing_client

MESSAGES = {
    CODE_OUT_OF_CREDITS: "Your workspace is out of credits. Buy more credits to keep uploading and syncing.",
    CODE_CREDITS_SUSPENDED: "Credits for this workspace are suspended. Contact support.",
}


def credits_refused(result: CreditCheck) -> HTTPException:
    code = result.code if result.code in MESSAGES else CODE_OUT_OF_CREDITS
    return HTTPException(status_code=402, detail={"code": code, "message": MESSAGES[code]})


def require_credits(workspace_id: Any, user_id: Any) -> None:
    """Raise 402 when the workspace may not start a paid operation."""
    result = get_billing_client().check(workspace_id, user_id)
    if not result.allowed:
        print(f"[Billing] Refused paid operation for workspace {canonical_uuid(workspace_id) or workspace_id}: {result.code}.")
        raise credits_refused(result)


async def require_credits_async(workspace_id: Any, user_id: Any) -> None:
    """``require_credits`` for async route handlers: the check is a blocking HTTP call."""
    result = await asyncio.to_thread(get_billing_client().check, workspace_id, user_id)
    if not result.allowed:
        print(f"[Billing] Refused paid operation for workspace {canonical_uuid(workspace_id) or workspace_id}: {result.code}.")
        raise credits_refused(result)


def background_check(workspace_id: Any, user_id: Any, what: str) -> CreditCheck:
    """The credit check for work nobody is waiting on. Logs when the workspace is skipped."""
    try:
        result = get_billing_client().check(workspace_id, user_id)
    except Exception as err:  # the client never raises, but a stand-in might
        print(f"[Billing] WARNING credit check for {what} failed ({err}); continuing.")
        return CreditCheck(True, source="fail_open")
    if not result.allowed:
        print(f"[Billing] Skipping {what} for workspace {canonical_uuid(workspace_id) or workspace_id}: {result.code}.")
    return result


def allowed_in_background(workspace_id: Any, user_id: Any, what: str) -> bool:
    return background_check(workspace_id, user_id, what).allowed


async def background_check_async(workspace_id: Any, user_id: Any, what: str) -> CreditCheck:
    return await asyncio.to_thread(background_check, workspace_id, user_id, what)


async def allowed_in_background_async(workspace_id: Any, user_id: Any, what: str) -> bool:
    return (await background_check_async(workspace_id, user_id, what)).allowed
