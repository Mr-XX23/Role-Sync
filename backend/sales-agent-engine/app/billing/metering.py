"""What the engine charges credits for (``docs/billing/credit-system-api.md``, the operation table).

Metering sits where all paid work passes, so a new caller is covered without doing anything:

- ``ModelRouter`` reports every model call that used tokens (planner, sub-agents, summaries, prospect
  briefs, skill drafts, and a failed attempt that had already produced tokens) to ``model_call``:
  ``agent.model_call`` (AGENT) with its tokens, or for a Google-grounded answer ``agent.web_answer``
  (SEARCH) with its tokens and one grounded prompt.
- ``MeteredWebSearch`` wraps Tavily: ``agent.web_search`` (SEARCH), one ``TAVILY_SEARCH`` per search answered.
- ``MeteredConnector`` wraps Composio: ``agent.connector_action`` (CONNECTORS), one ``COMPOSIO_EXECUTION``
  per action Composio ran, successful or not. A call that got no answer isn't charged: whether it ran is unknown.

Charges go to the workspace in the current ``usage_scope`` and are sent in the background, so they never
slow an answer down; work with no scope is not charged. Nothing here raises into the metered call.
"""

from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

from app.billing.client import BillingClient, TokensItem, UnitsItem, UsageCharge
from app.billing.scope import UsageScope, current_usage_scope
from app.models.types import TaskSpec, Usage
from app.platform.composio_client import ConnectorClient, ConnectorError, ConnectorOutcomeUnknown
from app.platform.web_search import TavilySearch, WebPage

logger = logging.getLogger(__name__)

MODEL_CALL = ("agent.model_call", "AGENT")
WEB_ANSWER = ("agent.web_answer", "SEARCH")
WEB_SEARCH = ("agent.web_search", "SEARCH")
CONNECTOR_ACTION = ("agent.connector_action", "CONNECTORS")


def grounded_prompt_unit(model: str) -> str:
    """Google prices a grounded prompt by model generation: Gemini 2.x, or 3.x (and later)."""
    name = model.strip().lower().removeprefix("models/")
    return "GROUNDED_PROMPT_25" if name.startswith("gemini-2") else "GROUNDED_PROMPT_3X"


class UsageMeter:
    def __init__(self, billing: BillingClient) -> None:
        self._billing = billing

    def model_call(self, task: TaskSpec, *, provider: str, model: str, usage: Usage, partial: bool = False) -> None:
        """One model call (or one failover attempt) that used tokens. ``partial``: it failed after using them."""
        try:
            scope = self._scope(f"the {task.purpose} call")
            if scope is None:
                return
            grounded = task.web_grounded
            if not grounded and not (usage.input_tokens or usage.output_tokens):
                logger.warning("the %s call on %s reported no token usage; nothing to charge", task.purpose, model)
                return
            items: tuple[TokensItem | UnitsItem, ...] = (
                TokensItem(
                    model=model,
                    input_tokens=usage.input_tokens,
                    cached_input_tokens=usage.cached_input_tokens,
                    output_tokens=usage.output_tokens,
                ),
            )
            if grounded:
                items += (UnitsItem(grounded_prompt_unit(model)),)
            metadata: dict[str, Any] = {"purpose": task.purpose, "provider": provider}
            if partial:
                metadata["partial"] = True
            self._submit(scope, WEB_ANSWER if grounded else MODEL_CALL, items, metadata)
        except Exception:
            logger.warning("could not meter the %s call", task.purpose, exc_info=True)

    def web_search(self) -> None:
        try:
            scope = self._scope("a web search")
            if scope is not None:
                self._submit(scope, WEB_SEARCH, (UnitsItem("TAVILY_SEARCH"),), {"provider": "tavily"})
        except Exception:
            logger.warning("could not meter a web search", exc_info=True)

    def connector_action(self, slug: str, *, successful: bool) -> None:
        try:
            scope = self._scope(f"connector action {slug}")
            if scope is not None:
                metadata = {"action": slug, "successful": successful}
                self._submit(scope, CONNECTOR_ACTION, (UnitsItem("COMPOSIO_EXECUTION"),), metadata)
        except Exception:
            logger.warning("could not meter connector action %s", slug, exc_info=True)

    def _scope(self, what: str) -> UsageScope | None:
        """Who pays for this, or ``None`` when nothing is charged (billing off, or no workspace in scope)."""
        if not self._billing.enabled:
            return None
        scope = current_usage_scope()
        if scope is None:
            logger.debug("%s ran with no workspace in scope; not charged", what)
        return scope

    def _submit(
        self, scope: UsageScope, kind: tuple[str, str], items: tuple[TokensItem | UnitsItem, ...], metadata: dict[str, Any]
    ) -> None:
        operation, category = kind
        self._billing.submit(
            UsageCharge(
                workspace_id=scope.workspace_id,
                user_id=scope.user_id,
                operation=operation,
                category=category,
                items=items,
                reference=scope.reference,
                metadata=metadata,
            )
        )


class MeteredWebSearch:
    """Tavily search that charges each search it gets an answer for (Tavily bills it, results or not)."""

    def __init__(self, search: TavilySearch, meter: UsageMeter) -> None:
        self._search = search
        self._meter = meter

    async def search(self, query: str, *, max_results: int, news_days: int | None = None) -> list[WebPage]:
        pages = await self._search.search(query, max_results=max_results, news_days=news_days)
        self._meter.web_search()
        return pages


class MeteredConnector:
    """The Composio connector, charging each action it runs. Same interface as ``ConnectorClient``."""

    def __init__(self, connector: ConnectorClient, meter: UsageMeter) -> None:
        self._connector = connector
        self._meter = meter

    async def has_active_connection(self, user_id: UUID, toolkit: str) -> bool:
        return await self._connector.has_active_connection(user_id, toolkit)

    async def execute(self, *, user_id: UUID, slug: str, arguments: dict[str, Any]) -> dict[str, Any]:
        try:
            data = await self._connector.execute(user_id=user_id, slug=slug, arguments=arguments)
        except ConnectorOutcomeUnknown:
            raise  # no answer: whether it ran is unknown, so it isn't charged
        except ConnectorError:
            self._meter.connector_action(slug, successful=False)  # Composio ran it and the app refused
            raise
        self._meter.connector_action(slug, successful=True)
        return data

    async def stage_file(self, *, slug: str, filename: str, content: bytes, mimetype: str) -> dict[str, str]:
        return await self._connector.stage_file(slug=slug, filename=filename, content=content, mimetype=mimetype)
