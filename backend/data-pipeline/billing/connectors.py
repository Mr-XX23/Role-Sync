"""Metering for connector work.

Composio bills every tool call. Each call site records one execution
(``billing.metering.record_composio_execution``); these decorators open the scope that collects them
and report the total once, as ``connector.sync`` (category CONNECTORS), when the run ends - however it
ends, since the executions were spent either way. The documents a run ingests are charged on their own
(``document.ingest``), by the ingestion pipeline.
"""
from __future__ import annotations

import asyncio
import functools
from typing import Any, Awaitable, Callable, TypeVar

from billing.charges import charge_connector_sync, new_run_id
from billing.metering import UsageMeter, execution_scope

F = TypeVar("F", bound=Callable[..., Awaitable[Any]])


def _connection_owner(manager: Any, connection_id: str) -> tuple[str, str]:
    """(workspace, user) of a sync manager's connection, or empty strings if it cannot be found."""
    store = getattr(manager, "store", None)
    conn = None
    lookup = getattr(store, "get_connection_by_id", None)
    if callable(lookup):
        try:
            conn = lookup(connection_id)
        except Exception:
            conn = None
    if conn is None:
        connections = getattr(store, "_connections", None)
        if isinstance(connections, dict):
            conn = connections.get(connection_id)
    if conn is None:
        return "", ""
    return str(getattr(conn, "tenant_id", "") or ""), str(getattr(conn, "user_id", "") or "")


def _trigger_name(trigger: Any) -> str:
    value = getattr(trigger, "value", trigger)
    return str(value or "")


async def report_executions(
    executions: UsageMeter,
    *,
    workspace_id: Any,
    user_id: Any,
    source: str,
    trigger: str,
    run_id: str = "",
    reference: Any = None,
) -> None:
    """Report a run's executions (if it made any) without blocking the event loop."""
    if executions.is_empty():
        return
    try:
        await asyncio.to_thread(
            charge_connector_sync,
            workspace_id=workspace_id,
            user_id=user_id,
            source=source,
            meter=executions,
            run_id=run_id or new_run_id(),
            trigger=trigger,
            reference=reference,
        )
    except Exception as err:  # never let billing break a sync
        print(f"[Billing] ERROR could not report {source} connector executions: {err}")


def metered_sync_run(source: str) -> Callable[[F], F]:
    """For a sync manager's job coroutine ``(self, connection_id, trigger_type=..., ...)``."""

    def decorate(job: F) -> F:
        @functools.wraps(job)
        async def run(self: Any, connection_id: str, *args: Any, **kwargs: Any) -> Any:
            run_id = new_run_id()
            with execution_scope() as executions:
                try:
                    return await job(self, connection_id, *args, **kwargs)
                finally:
                    workspace_id, user_id = _connection_owner(self, connection_id)
                    await report_executions(
                        executions,
                        workspace_id=workspace_id,
                        user_id=user_id,
                        source=source,
                        trigger=_trigger_name(kwargs.get("trigger_type", args[0] if args else "")),
                        run_id=run_id,
                        reference=connection_id,
                    )

        return run  # type: ignore[return-value]

    return decorate


def metered_webhook(source: str) -> Callable[[F], F]:
    """For a sync manager's ``process_webhook_event(self, event, ...)``.

    The event's workspace and user are read after it ran: managers align them with the connection the
    event was matched to.
    """

    def decorate(handler: F) -> F:
        @functools.wraps(handler)
        async def run(self: Any, event: Any, *args: Any, **kwargs: Any) -> Any:
            with execution_scope() as executions:
                try:
                    return await handler(self, event, *args, **kwargs)
                finally:
                    await report_executions(
                        executions,
                        workspace_id=getattr(event, "tenant_id", ""),
                        user_id=getattr(event, "user_id", ""),
                        source=source,
                        trigger="webhook",
                        reference=getattr(event, "external_id", None),
                    )

        return run  # type: ignore[return-value]

    return decorate
