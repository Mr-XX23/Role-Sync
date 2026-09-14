from __future__ import annotations

import pytest
from psycopg.conninfo import conninfo_to_dict

from app.config import Settings
from app.tools.registry import AgentScopes, ToolDefinition, ToolRegistry
from app.tools.types import ToolCategory, ToolInput, ToolKind, ToolScope
from tests.support import SideEffects, stub_registry


async def _noop(invocation):  # pragma: no cover - never called
    raise AssertionError


def _definition(**overrides) -> ToolDefinition:
    params = dict(
        name="t",
        description="d",
        kind=ToolKind.WRITE,
        scope=ToolScope.COMMUNICATION,
        category=ToolCategory.ACTION,
        input_model=ToolInput,
        handler=_noop,
    )
    params.update(overrides)
    return ToolDefinition(**params)


def test_read_tools_must_have_read_scope_and_writes_must_not():
    with pytest.raises(ValueError):
        _definition(kind=ToolKind.READ, scope=ToolScope.COMMUNICATION)
    with pytest.raises(ValueError):
        _definition(kind=ToolKind.WRITE, scope=ToolScope.READ)


def test_duplicate_tool_names_are_refused():
    registry = ToolRegistry([_definition()])
    with pytest.raises(ValueError):
        registry.register(_definition())


def test_scope_map_keeps_research_read_only():
    registry = stub_registry(SideEffects())
    scopes = AgentScopes()
    assert [d.name for d in scopes.tools_for("research", registry)] == ["lookup_facts"]
    assert {d.name for d in scopes.tools_for("outreach", registry)} == {
        "lookup_facts", "send_note", "broken_send", "unconfirmed_send"
    }
    assert scopes.tools_for("unknown-agent", registry) == []


def _full_registry() -> ToolRegistry:
    """The production tool set, built over doubles (nothing is called)."""
    from unittest.mock import AsyncMock, MagicMock

    import httpx

    from app.container import default_registry
    from app.engine.guardrails.saga import Compensator
    from app.tools.adapters.memory import memory_tools
    from tests.support import FakeConnector

    router = MagicMock()
    router.can_serve.return_value = True
    settings = Settings(tavily_api_key=None, composio_api_key=None)
    registry = default_registry(
        settings, connector=FakeConnector(), router=router, http=httpx.AsyncClient(), workspaces=AsyncMock(), deals=AsyncMock()
    )
    registry.register(Compensator(ledger=MagicMock(), registry=registry, executor=MagicMock()).tool())
    for definition in memory_tools(MagicMock(), MagicMock(), AsyncMock(), AsyncMock()):
        registry.register(definition)
    return registry


def test_every_write_tool_shows_the_reviewer_a_preview_and_says_how_to_undo_it():
    registry = _full_registry()
    writes = {d.name: d for d in registry.all() if d.kind is ToolKind.WRITE}
    assert set(writes) == {
        "send_email", "create_calendar_event", "send_slack_message", "create_notion_page", "generate_document",
        "create_quote", "create_catalog_item", "update_catalog_item", "record_stock_movement", "correct_stock_count",
        "reserve_stock", "release_stock", "retire_catalog_item", "undo_actions", "create_deal", "update_deal",
        "add_web_page_to_knowledge_base", "update_knowledge_document", "reclassify_knowledge_document",
        "reindex_knowledge_document", "delete_knowledge_document", "save_catalog_category", "delete_catalog_category",
        "create_stock_location", "update_stock_location", "delete_stock_location", "add_catalog_skus", "restore_catalog_item",
        "update_my_profile", "update_my_preferences", "sync_app_now", "change_app_sync_settings", "set_app_auto_sync",
        "disconnect_app",
    }
    assert all(d.preview is not None for d in writes.values())
    # Only these can't be reversed: a sent email, a released reservation, an undo itself, and indexing a document
    # again (nothing to put back). A stock movement has an undo handler for shipments, and deleting a document one
    # for web pages (added again from their address); other movements and deleted files report that they can't be.
    # A sync can't be taken back, and a disconnected app needs the rep to sign in again in a browser.
    assert {name for name, d in writes.items() if d.undo_handler is None} == {
        "send_email", "release_stock", "undo_actions", "reindex_knowledge_document", "sync_app_now", "disconnect_app"
    }
    assert {name for name, d in writes.items() if d.irreversible} == {
        "send_email", "undo_actions", "delete_knowledge_document", "disconnect_app"
    }


def test_sub_agent_scopes_stay_narrow_over_the_full_tool_set():
    registry = _full_registry()
    scopes = AgentScopes()
    assert all(d.kind is ToolKind.READ for d in scopes.tools_for("research", registry))
    assert {d.name for d in scopes.tools_for("quote", registry) if d.kind is ToolKind.WRITE} == {
        "generate_document", "create_quote", "create_catalog_item", "update_catalog_item", "record_stock_movement",
        "correct_stock_count", "reserve_stock", "release_stock", "retire_catalog_item",
    }
    assert {d.name for d in scopes.tools_for("outreach", registry) if d.kind is ToolKind.WRITE} == {
        "send_email", "create_calendar_event", "send_slack_message", "create_notion_page",
    }
    assert "undo_actions" in {d.name for d in scopes.tools_for("orchestrator", registry)}
    # Sub-agents read the knowledge base but only the coordinator changes or deletes what is in it.
    knowledge = {d.name for d in registry.all() if d.scope is ToolScope.KNOWLEDGE}
    assert knowledge == {
        "add_web_page_to_knowledge_base", "update_knowledge_document", "reclassify_knowledge_document",
        "reindex_knowledge_document", "delete_knowledge_document",
    }
    assert not knowledge & {d.name for agent in ("research", "outreach", "quote") for d in scopes.tools_for(agent, registry)}
    assert knowledge <= {d.name for d in scopes.tools_for("orchestrator", registry)}
    # The quote agent prices and holds stock; setting up categories, locations and SKUs is the coordinator's.
    setup = {d.name for d in registry.all() if d.scope is ToolScope.CATALOG_SETUP}
    assert setup == {
        "save_catalog_category", "delete_catalog_category", "create_stock_location", "update_stock_location",
        "delete_stock_location", "add_catalog_skus", "restore_catalog_item",
    }
    assert not setup & {d.name for agent in ("research", "outreach", "quote") for d in scopes.tools_for(agent, registry)}
    assert setup <= {d.name for d in scopes.tools_for("orchestrator", registry)}
    # Every agent can read the rep's profile (an outreach email needs their signature); only the coordinator changes it.
    profile = {d.name for d in registry.all() if d.scope is ToolScope.PROFILE}
    assert profile == {"update_my_profile", "update_my_preferences"}
    assert not profile & {d.name for agent in ("research", "outreach", "quote") for d in scopes.tools_for(agent, registry)}
    assert profile <= {d.name for d in scopes.tools_for("orchestrator", registry)}
    assert all("get_my_profile" in {d.name for d in scopes.tools_for(agent, registry)} for agent in ("research", "outreach", "quote"))
    # Every agent can see the rep's connected apps; only the coordinator syncs, reconfigures or disconnects them.
    connectors = {d.name for d in registry.all() if d.scope is ToolScope.CONNECTORS}
    assert connectors == {"sync_app_now", "change_app_sync_settings", "set_app_auto_sync", "disconnect_app"}
    assert not connectors & {d.name for agent in ("research", "outreach", "quote") for d in scopes.tools_for(agent, registry)}
    assert connectors <= {d.name for d in scopes.tools_for("orchestrator", registry)}
    assert {"list_connected_apps", "get_app_sync_history"} <= {d.name for d in scopes.tools_for("research", registry)}
    assert {"list_catalog_items", "get_catalog_item", "describe_catalog", "list_stock_reservations"} <= {
        d.name for d in scopes.tools_for("research", registry)
    }
    assert {"list_knowledge_documents", "search_knowledge_base"} <= {d.name for d in scopes.tools_for("research", registry)}
    # The agent's memory needs its own scope: no sub-agent has it yet.
    memory = {d.name for d in registry.all() if d.kind is ToolKind.MEMORY}
    assert memory == {"remember", "forget"}
    assert not memory & {d.name for agent in ("research", "outreach", "quote") for d in scopes.tools_for(agent, registry)}
    assert memory <= {d.name for d in scopes.tools_for("orchestrator", registry)}


def test_database_urls_are_derived_safely_from_one_source():
    settings = Settings(database_url="postgresql://svc:p%40ss%3Aword@db.internal:5433/agentdb")
    assert settings.sqlalchemy_url.drivername == "postgresql+asyncpg"
    assert settings.sqlalchemy_url.password == "p@ss:word"
    parts = conninfo_to_dict(settings.psycopg_conninfo)
    assert parts == {"host": "db.internal", "port": "5433", "dbname": "agentdb", "user": "svc", "password": "p@ss:word"}
