"""Which workspace pays for the work running right now.

A context variable, so every model call, web search and connector action is charged to the right
workspace without it being passed down: the session runner starts each run segment in a context that
carries the session's scope (the planner, sub-agents, summaries and tools all inherit it), and work
outside a run (an AI skill draft) opens a scope around itself. Work with no scope is not charged.
"""

from __future__ import annotations

import contextvars
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from uuid import UUID


@dataclass(frozen=True, slots=True)
class UsageScope:
    workspace_id: UUID
    user_id: UUID | None = None
    reference: str | None = None  # the session (or other job) the usage belongs to


_current: contextvars.ContextVar[UsageScope | None] = contextvars.ContextVar("billing_usage_scope", default=None)


def current_usage_scope() -> UsageScope | None:
    return _current.get()


@contextmanager
def usage_scope(workspace_id: UUID, user_id: UUID | None = None, *, reference: str | None = None) -> Iterator[UsageScope]:
    """Charge the work done inside this block to ``workspace_id``."""
    scope = UsageScope(workspace_id=workspace_id, user_id=user_id, reference=reference)
    token = _current.set(scope)
    try:
        yield scope
    finally:
        _current.reset(token)


def context_with_usage_scope(
    workspace_id: UUID, user_id: UUID | None = None, *, reference: str | None = None
) -> contextvars.Context:
    """A copy of the current context in which work is charged to ``workspace_id``, for
    ``asyncio.create_task(..., context=...)``: the task and every task it starts inherit the scope."""
    context = contextvars.copy_context()
    context.run(_current.set, UsageScope(workspace_id=workspace_id, user_id=user_id, reference=reference))
    return context
