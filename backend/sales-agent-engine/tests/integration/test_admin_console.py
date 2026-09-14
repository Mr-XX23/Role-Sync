"""Super Admin Console against the real database: metering, sessions, stop, pause, prompts, routes, rates, tools, audit.
auth-service's platform-access check is replaced by a guard that knows one super admin."""

from __future__ import annotations

import asyncio
from uuid import UUID, uuid4

import pytest

from app.admin.guard import AdminActor, NotSuperAdmin
from app.config import API_PREFIX
from app.core.enums import PendingActionStatus, SessionStatus
from tests.integration.conftest import all_events
from tests.integration.test_chat_flow import _asgi_client, _gmail_registry, _headers, _wait_for_status
from tests.support import FakeConnector, ScriptedBrain, make_token

pytestmark = pytest.mark.integration

ADMIN = f"{API_PREFIX}/admin"


class OneSuperAdmin:
    def __init__(self, admin_id: UUID) -> None:
        self.admin_id = admin_id

    async def require_super_admin(self, principal):
        if principal.user_id != self.admin_id:
            raise NotSuperAdmin("no")
        return AdminActor(user_id=principal.user_id, email="boss@rolesync.test")


async def test_admin_console_end_to_end(make_container, rsa_keys, tenant_id, user_id):
    container = await make_container(providers={"gemini": ScriptedBrain()}, registry=_gmail_registry(FakeConnector()))
    admin_id = uuid4()
    container.admin_guard = OneSuperAdmin(admin_id)
    rep = _headers(rsa_keys, user_id, tenant_id)
    boss = {"Cookie": f"access_token={make_token(rsa_keys, admin_id)}"}

    async with _asgi_client(container) as client:
        assert (await client.get(f"{ADMIN}/overview", headers=rep)).status_code == 403

        started = (await client.post(f"{API_PREFIX}/chat", headers=rep, json={"message": "Email Jane"})).json()
        session_id = UUID(started["session_id"])
        await _wait_for_status(container, session_id, SessionStatus.AWAITING_APPROVAL)

        overview = (await client.get(f"{ADMIN}/overview", headers=boss)).json()
        assert overview["awaiting_approval"] >= 1 and overview["today"]["calls"] >= 1 and len(overview["daily"]) == 14

        usage = (await client.get(f"{ADMIN}/usage", headers=boss, params={"days": 7})).json()
        scripted = next(row for row in usage["by_model"] if row["model"] == "scripted-gemini")
        assert scripted["calls"] >= 1 and scripted["priced"] is False and usage["totals"]["unpriced_calls"] >= 1
        assert any(row["workspace_id"] == str(tenant_id) for row in usage["by_workspace"])
        assert len(usage["daily"]) == 7

        sessions = (await client.get(f"{ADMIN}/sessions", headers=boss, params={"status": "AWAITING_APPROVAL"})).json()
        mine = next(row for row in sessions if row["id"] == str(session_id))
        assert mine["stop_requested"] is False and mine["turns"] == 1

        stopped = await client.post(f"{ADMIN}/sessions/{session_id}/stop", headers=boss)
        assert stopped.status_code == 200 and stopped.json()["stop_requested"] is True
        await _wait_for_status(container, session_id, SessionStatus.HALTED)
        [action] = await container.pending_actions.list_for_user(tenant_id=tenant_id, user_id=user_id)
        assert action.status == PendingActionStatus.EXPIRED
        halted = [e for e in await all_events(container, session_id) if e["type"] == "halted"]
        assert halted and halted[-1]["data"]["reason"] == "ADMIN_STOP"
        assert await container.admin.stop_requested([session_id]) == set()  # consumed by the halt
        assert (await client.post(f"{ADMIN}/sessions/{session_id}/stop", headers=boss)).status_code == 409

        controls = (await client.get(f"{ADMIN}/controls", headers=boss)).json()
        body = {
            "agent_enabled": False,
            "maintenance_message": "Maintenance until noon",
            "sub_agents_enabled": controls["sub_agents_enabled"],
            "web_search_enabled": controls["web_search_enabled"],
            "limits": {"max_steps_per_turn": 9},
        }
        saved = (await client.put(f"{ADMIN}/controls", headers=boss, json=body)).json()
        assert saved["version"] == 1 and saved["limits"]["max_steps_per_turn"]["value"] == 9
        paused = await client.post(f"{API_PREFIX}/chat", headers=rep, json={"message": "Email Jane"})
        assert paused.status_code == 503 and paused.json()["message"] == "Maintenance until noon"
        await client.put(f"{ADMIN}/controls", headers=boss, json=body | {"agent_enabled": True, "limits": {}})

        tools = (await client.get(f"{ADMIN}/tools", headers=boss)).json()
        assert any(tool["name"] == "send_email" and tool["enabled"] and tool["available_to"] for tool in tools)
        off = (await client.put(f"{ADMIN}/tools/send_email", headers=boss, json={"enabled": False})).json()
        assert off["enabled"] is False and not container.registry.is_enabled("send_email")

        models = (await client.put(f"{ADMIN}/models/routes/complex", headers=boss, json={"provider": "openrouter", "models": ["a/b", "c:free"]})).json()
        complex_route = next(route for route in models["routes"] if route["route"] == "complex")
        assert complex_route["overridden"] and container.router.rules.complex.models == ("a/b", "c:free")
        reset = (await client.put(f"{ADMIN}/models/routes/complex", headers=boss, json={"reset": True})).json()
        assert not next(route for route in reset["routes"] if route["route"] == "complex")["overridden"]
        rates = (
            await client.put(
                f"{ADMIN}/models/rates",
                headers=boss,
                json={"rates": [{"provider": "gemini", "model": "scripted-gemini", "input_per_million_usd": 1, "output_per_million_usd": 2, "request_fee_usd": 0.01}]},
            )
        ).json()
        assert any(rate["model"] == "scripted-gemini" and rate["source"] == "custom" for rate in rates["rates"])
        usage = (await client.get(f"{ADMIN}/usage", headers=boss, params={"days": 1})).json()
        assert next(row for row in usage["by_model"] if row["model"] == "scripted-gemini")["cost_usd"] > 0

        published = (await client.post(f"{ADMIN}/prompts/research", headers=boss, json={"mode": "APPEND", "instructions": "Be brief."})).json()
        assert published["active"]["version"] == 1
        await client.post(f"{ADMIN}/prompts/research", headers=boss, json={"mode": "APPEND", "instructions": ""})
        restored = (await client.post(f"{ADMIN}/prompts/research/versions/1/restore", headers=boss)).json()
        assert restored["active"]["version"] == 3 and container.admin.prompt_body("research", "B").endswith("Be brief.")

        await asyncio.sleep(0)
        audit = (await client.get(f"{ADMIN}/audit", headers=boss)).json()
        actions = {entry["action"] for entry in audit}
        assert {"session.stopped", "agent.paused", "agent.resumed", "tool.disabled", "model.route_updated", "model.rates_updated", "prompt.published", "prompt.restored"} <= actions
        assert all(entry["service"] == "agent" and entry["actor_email"] == "boss@rolesync.test" for entry in audit)
