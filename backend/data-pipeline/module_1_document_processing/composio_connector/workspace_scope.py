"""Background connector jobs act only on connections that belong to a workspace.

Connector routes act only inside a workspace the caller is a member of, so every
connection they save is keyed by that workspace's id. Connections saved before that -
under ``tenant_default`` (the old header default) or another made-up tenant - can no
longer be reached, reconfigured or disconnected through the API, and nothing synced into
them is visible in any workspace. Scheduled syncs and sweeps leave them alone rather than
spend Composio executions and embedding quota on them; the user reconnects from a
workspace instead.
"""

from __future__ import annotations

from typing import Iterable, TypeVar

from module_1_document_processing.workspace_access import is_workspace_id

C = TypeVar("C")

_reported: set[str] = set()


def workspace_connections(connections: Iterable[C], job: str) -> list[C]:
    """The connections a background job may act on. Each one left out is reported once."""
    kept: list[C] = []
    for conn in connections:
        if is_workspace_id(getattr(conn, "tenant_id", None)):
            kept.append(conn)
            continue
        connection_id = getattr(conn, "connection_id", "")
        if connection_id not in _reported:
            _reported.add(connection_id)
            print(
                f"[{job}] Skipping {connection_id}: it was saved outside a workspace, so nobody can "
                "see or manage what it syncs. Reconnect it from a workspace."
            )
    return kept
