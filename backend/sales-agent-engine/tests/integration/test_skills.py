"""Skills through the real API, store, gate and orchestrator (decided 2026-09-14).

- who sees and changes which skills; per-rep switches and the admin switch for everyone
- every save is a version; archiving and resetting are recoverable; SKILL.md in and out; AI drafts
- the agent: its instructions list the switched-on skills, it loads one with use_skill, a skill the rep
  picked is loaded before the model's first step, and a skill handed to a sub-agent is loaded in its own
  conversation. The model and workspace-service are doubles; Postgres and Redis are real.
"""

from __future__ import annotations

import asyncio
import json
from contextlib import asynccontextmanager
from typing import Any
from uuid import UUID, uuid4

import httpx
import pytest

from app.config import API_PREFIX
from app.core.enums import SessionStatus
from app.engine.delegation import DELEGATE_TOOL
from app.engine.orchestrator import turn_input
from app.engine.runner import context_for
from app.main import create_app
from app.models.types import Completion, Message, Role, StreamDone, TextDelta, ToolCall, Usage
from app.skills.builtins import BUILTIN_BY_KEY, BUILTIN_SKILLS
from app.skills.service import INDEX_HEADER, SKILL_TOOL
from tests.integration.conftest import open_session, settle_runs, start_run
from tests.support import make_token

pytestmark = pytest.mark.integration

SKILLS = f"{API_PREFIX}/skills"
INSTRUCTIONS = "# Renewal play\n\n1. `recall` what we know about the account.\n2. Draft a short renewal note with the three things they valued."
BODY = {
    "name": "Renewal nudge",
    "description": "Use when a customer's renewal is due within 60 days.",
    "instructions": INSTRUCTIONS,
    "category": "PIPELINE",
    "tools": ["recall"],
}


def _headers(rsa_keys, user: UUID, workspace: UUID) -> dict[str, str]:
    return {"Cookie": f"access_token={make_token(rsa_keys, user)}", "X-Tenant-Id": str(workspace)}


@asynccontextmanager
async def _api(container):
    app = create_app(container.settings)
    app.state.container = container
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://engine.test") as client:
        yield client


def _people(workspace_service, tenant_id: UUID, **roles: str) -> dict[str, UUID]:
    people = {}
    for name, role in roles.items():
        person = uuid4()
        workspace_service.add(person, tenant_id)
        workspace_service.roles[(person, tenant_id)] = role
        people[name] = person
    return people


def _by_ref(listing: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {skill["ref"]: skill for skill in listing["skills"]}


# --------------------------------------------------------------------------- the app


async def test_everyone_sees_the_built_ins_admins_share_skills_and_reps_keep_their_own(make_container, rsa_keys, tenant_id, user_id, workspace_service):
    people = _people(workspace_service, tenant_id, owner="OWNER", viewer="VIEWER")
    container = await make_container()
    member, owner, viewer = (_headers(rsa_keys, who, tenant_id) for who in (user_id, people["owner"], people["viewer"]))

    async with _api(container) as client:
        listed = (await client.get(SKILLS, headers=member)).json()
        assert [skill["ref"] for skill in listed["skills"]] == [builtin.key for builtin in BUILTIN_SKILLS]
        assert all(skill["enabled"] and skill["source"] == "BUILTIN" and not skill["editable"] for skill in listed["skills"])
        assert (listed["can_create_private"], listed["can_manage_workspace"], listed["limits"]["enabled"]) == (True, False, 10)
        assert _by_ref(listed)["meeting-follow-up"]["apps"] == ["Gmail", "Google Calendar"]

        assert (await client.post(SKILLS, json=BODY | {"visibility": "WORKSPACE"}, headers=member)).status_code == 403
        assert (await client.post(SKILLS, json=BODY, headers=viewer)).status_code == 403
        mine = await client.post(SKILLS, json=BODY, headers=member)
        assert mine.status_code == 201, mine.text
        mine = mine.json()
        assert (mine["source"], mine["slug"], mine["editable"], mine["version"], mine["instructions"]) == (
            "PRIVATE", "renewal-nudge", True, 1, INSTRUCTIONS
        )
        assert (await client.post(SKILLS, json=BODY, headers=member)).json()["slug"] == "renewal-nudge-2"  # same name, own id
        unknown_tool = await client.post(SKILLS, json=BODY | {"tools": ["wire_money"]}, headers=member)
        assert unknown_tool.status_code == 422 and "no tool called wire_money" in unknown_tool.text

        shared = await client.post(SKILLS, json=BODY | {"name": "Team renewal play", "visibility": "WORKSPACE"}, headers=owner)
        assert shared.status_code == 201
        shared = shared.json()

        for_member = _by_ref((await client.get(SKILLS, headers=member)).json())
        for_owner = _by_ref((await client.get(SKILLS, headers=owner)).json())
        assert for_member[shared["ref"]]["source"] == "WORKSPACE" and not for_member[shared["ref"]]["editable"]
        assert mine["ref"] in for_member and mine["ref"] not in for_owner  # private means private, admins included
        assert (await client.get(f"{SKILLS}/{mine['ref']}", headers=owner)).status_code == 404

        edit = BODY | {"name": "Team renewal play", "instructions": INSTRUCTIONS + "\n3. Offer a call.", "expected_version": 1}
        assert (await client.put(f"{SKILLS}/{shared['ref']}", json=edit, headers=member)).status_code == 403
        saved = await client.put(f"{SKILLS}/{shared['ref']}", json=edit, headers=owner)
        assert saved.status_code == 200 and saved.json()["version"] == 2 and saved.json()["instructions"].endswith("Offer a call.")
        stale = await client.put(f"{SKILLS}/{shared['ref']}", json=edit, headers=owner)
        assert stale.status_code == 409 and "changed by someone else" in stale.text


async def test_switches_are_per_rep_and_admins_can_switch_a_skill_off_for_everyone(make_container, rsa_keys, tenant_id, user_id, workspace_service, monkeypatch):
    people = _people(workspace_service, tenant_id, owner="OWNER")
    container = await make_container()
    member, owner = _headers(rsa_keys, user_id, tenant_id), _headers(rsa_keys, people["owner"], tenant_id)
    research = f"{SKILLS}/prospect-research-brief"

    async with _api(container) as client:
        off = (await client.put(f"{research}/enabled", json={"enabled": False}, headers=member)).json()
        assert (off["enabled"], off["my_switch"], off["workspace_enabled"]) == (False, False, True)
        assert _by_ref((await client.get(SKILLS, headers=owner)).json())["prospect-research-brief"]["enabled"]  # only my agent

        assert (await client.put(f"{research}/workspace-enabled", json={"enabled": False}, headers=member)).status_code == 403
        await client.put(f"{SKILLS}/lead-qualification/workspace-enabled", json={"enabled": False}, headers=owner)
        qualification = _by_ref((await client.get(SKILLS, headers=member)).json())["lead-qualification"]
        assert (qualification["enabled"], qualification["workspace_enabled"]) == (False, False)
        blocked = await client.put(f"{SKILLS}/lead-qualification/enabled", json={"enabled": True}, headers=member)
        assert blocked.status_code == 409 and "switched" in blocked.text and "off for everyone" in blocked.text

        await client.put(f"{SKILLS}/lead-qualification/workspace-enabled", json={"enabled": True}, headers=owner)
        assert _by_ref((await client.get(SKILLS, headers=member)).json())["lead-qualification"]["enabled"]
        private = (await client.post(SKILLS, json=BODY, headers=member)).json()
        assert (await client.put(f"{SKILLS}/{private['ref']}/workspace-enabled", json={"enabled": False}, headers=owner)).status_code == 404

        # Every switched-on skill is a line in the agent's instructions, so there is a ceiling.
        monkeypatch.setattr("app.skills.service.MAX_ENABLED", 10)
        full = await client.put(f"{research}/enabled", json={"enabled": True}, headers=member)
        assert full.status_code == 409 and "up to 10 skills" in full.text
        await client.put(f"{SKILLS}/{private['ref']}/enabled", json={"enabled": False}, headers=member)
        assert (await client.put(f"{research}/enabled", json={"enabled": True}, headers=member)).json()["enabled"]


async def test_every_save_is_a_version_and_archived_or_customized_skills_can_be_brought_back(make_container, rsa_keys, tenant_id, user_id, workspace_service):
    people = _people(workspace_service, tenant_id, owner="OWNER")
    container = await make_container()
    member, owner = _headers(rsa_keys, user_id, tenant_id), _headers(rsa_keys, people["owner"], tenant_id)

    async with _api(container) as client:
        skill = (await client.post(SKILLS, json=BODY | {"visibility": "WORKSPACE"}, headers=owner)).json()
        ref = skill["ref"]
        for version, extra in ((1, "\n3. Offer a call."), (2, "\n3. Offer a workshop.")):
            await client.put(f"{SKILLS}/{ref}", json=BODY | {"instructions": INSTRUCTIONS + extra, "expected_version": version}, headers=owner)

        versions = (await client.get(f"{SKILLS}/{ref}/versions", headers=member)).json()
        assert [item["version"] for item in versions] == [3, 2, 1] and versions[1]["instructions"].endswith("Offer a call.")
        assert not versions[0]["edited_by_me"]  # the member is reading the owner's history
        restored = await client.post(f"{SKILLS}/{ref}/versions/1/restore", json={"expected_version": 3}, headers=owner)
        assert restored.json()["version"] == 4 and restored.json()["instructions"] == INSTRUCTIONS
        latest = (await client.get(f"{SKILLS}/{ref}/versions", headers=owner)).json()[0]
        assert (latest["note"], latest["edited_by_me"]) == ("Restored from version 1", True)

        assert (await client.delete(f"{SKILLS}/{ref}", headers=member)).status_code == 403
        archived = await client.delete(f"{SKILLS}/{ref}", headers=owner)
        assert archived.status_code == 200 and archived.json()["archived_at"]
        assert ref not in _by_ref((await client.get(SKILLS, headers=owner)).json())
        assert [item["id"] for item in (await client.get(f"{SKILLS}/archived", headers=owner)).json()] == [ref]
        assert (await client.get(f"{SKILLS}/archived", headers=member)).json() == []  # workspace skills come back through admins
        back = await client.post(f"{SKILLS}/archived/{ref}/restore", headers=owner)
        assert back.status_code == 200 and back.json()["version"] == 4 and ref in _by_ref((await client.get(SKILLS, headers=member)).json())

        # A built-in: customized for the workspace, then reset to what ships.
        builtin = BUILTIN_BY_KEY["discovery-call-prep"]
        custom = BODY | {"name": "Discovery call prep", "description": builtin.content.description, "category": "ENGAGE", "expected_version": builtin.version}
        assert (await client.put(f"{SKILLS}/discovery-call-prep", json=custom, headers=member)).status_code == 403
        customized = (await client.put(f"{SKILLS}/discovery-call-prep", json=custom, headers=owner)).json()
        assert (customized["source"], customized["customized"], customized["instructions"]) == ("BUILTIN", True, INSTRUCTIONS)
        assert (await client.get(f"{SKILLS}/discovery-call-prep", headers=member)).json()["instructions"] == INSTRUCTIONS
        [first] = (await client.get(f"{SKILLS}/discovery-call-prep/versions", headers=owner)).json()
        assert first["note"].startswith("Customized from the built-in skill")

        reset = await client.delete(f"{SKILLS}/discovery-call-prep", headers=owner)
        assert reset.status_code == 200
        shipped = (await client.get(f"{SKILLS}/discovery-call-prep", headers=member)).json()
        assert (shipped["customized"], shipped["instructions"]) == (False, builtin.content.instructions)
        refused = await client.delete(f"{SKILLS}/discovery-call-prep", headers=owner)
        assert refused.status_code == 400 and "built in" in refused.text


async def test_skill_md_files_come_in_through_a_preview_and_go_out_as_downloads(make_container, rsa_keys, tenant_id, user_id, workspace_service):
    people = _people(workspace_service, tenant_id, owner="OWNER")
    container = await make_container()
    member, owner = _headers(rsa_keys, user_id, tenant_id), _headers(rsa_keys, people["owner"], tenant_id)
    file = (
        "---\nname: renewal-call-prep\ndescription: Use when a renewal call is booked.\n"
        "allowed-tools: Bash, recall\nmetadata:\n  category: PIPELINE\n---\n" + INSTRUCTIONS
    )

    async with _api(container) as client:
        preview = await client.post(f"{SKILLS}/import/preview", json={"content": file}, headers=member)
        assert preview.status_code == 200
        draft = preview.json()
        assert (draft["name"], draft["category"], draft["tools"]) == ("Renewal call prep", "PIPELINE", ["recall"])
        assert draft["warnings"] == ["Tools this agent doesn't have were left out: Bash"]
        broken = await client.post(f"{SKILLS}/import/preview", json={"content": "no header at all"}, headers=member)
        assert broken.status_code == 422 and "starts with a block" in broken.text

        fields = {key: draft[key] for key in ("name", "description", "instructions", "category", "tools")}
        saved = (await client.post(SKILLS, json=fields | {"note": "Imported from SKILL.md"}, headers=member)).json()
        assert (await client.get(f"{SKILLS}/{saved['ref']}/versions", headers=member)).json()[0]["note"] == "Imported from SKILL.md"

        exported = await client.get(f"{SKILLS}/{saved['ref']}/export", headers=member)
        assert exported.headers["content-type"].startswith("text/markdown")
        assert exported.headers["content-disposition"] == 'attachment; filename="renewal-call-prep-SKILL.md"'
        assert exported.text.startswith("---\nname: renewal-call-prep\n") and INSTRUCTIONS in exported.text
        assert (await client.get(f"{SKILLS}/{saved['ref']}/export", headers=owner)).status_code == 404
        again = await client.post(f"{SKILLS}/import/preview", json={"content": exported.text}, headers=owner)
        assert again.json()["instructions"] == INSTRUCTIONS  # what goes out comes back in


class DraftingModel:
    name = "gemini"

    def __init__(self) -> None:
        self.tasks: list[Any] = []

    async def stream(self, task: Any, models: Any):
        self.tasks.append(task)
        text = (
            "```markdown\n---\nname: renewal-risk-check\ndescription: Use when a renewal is coming up and the rep wants to know "
            "if the customer might leave.\nmetadata:\n  display_name: Renewal risk check\n  category: PIPELINE\n"
            "  tools: [recall, search_everything]\n---\n# Renewal risk check\n\n1. `recall` the account.\n2. List warning signs "
            "and what to do about each.\n```"
        )
        yield TextDelta(text)
        yield StreamDone(Completion(message=Message(role=Role.ASSISTANT, content=text), provider="gemini", model="scripted", usage=Usage(10, 10)))


async def test_a_skill_is_drafted_with_ai_from_one_sentence_within_a_daily_limit(make_container, rsa_keys, tenant_id, user_id, workspace_service):
    people = _people(workspace_service, tenant_id, viewer="VIEWER")
    model = DraftingModel()
    container = await make_container(providers={"gemini": model}, settings_overrides={"skill_drafts_per_day": 1})
    idea = {"idea": "Check whether customers with renewals coming up might churn"}

    async with _api(container) as client:
        assert (await client.post(f"{SKILLS}/draft", json=idea, headers=_headers(rsa_keys, people["viewer"], tenant_id))).status_code == 403
        drafted = await client.post(f"{SKILLS}/draft", json=idea, headers=_headers(rsa_keys, user_id, tenant_id))
        assert drafted.status_code == 200, drafted.text
        assert (drafted.json()["name"], drafted.json()["tools"]) == ("Renewal risk check", ["recall"])
        assert drafted.json()["warnings"] == ["Tools this agent doesn't have were left out: search_everything"]
        assert (await client.get(SKILLS, headers=_headers(rsa_keys, user_id, tenant_id))).json()["limits"]["private"] == 0  # nothing saved
        again = await client.post(f"{SKILLS}/draft", json=idea, headers=_headers(rsa_keys, user_id, tenant_id))
        assert again.status_code == 429

    [task] = model.tasks
    assert "- recall:" in task.system and f"- {SKILL_TOOL}:" not in task.system and "Check whether customers" in task.messages[0].content


# --------------------------------------------------------------------------- the agent


class SkillfulBrain:
    """Plays the orchestrator (and the research sub-agent): loads ``choose`` first if told to, then answers,
    saying which skill it had in front of it."""

    name = "gemini"

    def __init__(self, choose: str | None = None, delegate_with: str | None = None) -> None:
        self.tasks: list[Any] = []
        self.choose = choose
        self.delegate_with = delegate_with

    def _decide(self, task: Any) -> tuple[str, list[tuple[str, dict[str, Any]]]]:
        messages = list(task.messages)
        loaded = [json.loads(m.content) for m in messages if m.role is Role.TOOL and m.name == SKILL_TOOL]
        names = [item.get("data", {}).get("name") for item in loaded]
        if task.purpose == "subagent:research":
            return f"Brief written following: {', '.join(map(str, names)) or 'no skill'}", []
        if self.delegate_with:
            delegated = [json.loads(m.content) for m in messages if m.role is Role.TOOL and m.name == DELEGATE_TOOL]
            if not delegated:
                return "", [(DELEGATE_TOOL, {"agent": "research", "task": "Work out how we beat Globex at Acme", "skill": self.delegate_with})]
            return f"Done: {delegated[0]['data']['answer']}", []
        if self.choose and not loaded:
            return "", [(SKILL_TOOL, {"skill": self.choose})]
        return f"Done following: {', '.join(map(str, names)) or 'no skill'}", []

    async def stream(self, task: Any, models: Any):
        self.tasks.append(task)
        content, calls = self._decide(task)
        if content:
            yield TextDelta(content)
        message = Message(
            role=Role.ASSISTANT,
            content=content,
            tool_calls=tuple(ToolCall(id=f"c{len(self.tasks)}_{i}", name=n, arguments=a) for i, (n, a) in enumerate(calls)),
        )
        yield StreamDone(Completion(message=message, provider="gemini", model="scripted", usage=Usage(50, 10)))


async def _done(container, session_id: UUID, timeout: float = 20.0) -> None:
    deadline = asyncio.get_running_loop().time() + timeout
    while asyncio.get_running_loop().time() < deadline:
        await settle_runs(container)
        if (await container.sessions.get(session_id)).status == SessionStatus.DONE:
            return
        await asyncio.sleep(0.05)
    raise AssertionError(f"session never finished: {(await container.sessions.get(session_id)).status}")


async def _usage(container, tenant_id: UUID, user_id: UUID, ref: str):
    return (await container.skills.entry(tenant_id, user_id, ref)).usage


async def test_the_agent_lists_its_switched_on_skills_and_loads_the_one_a_request_matches(make_container, tenant_id, user_id, workspace_service):
    brain = SkillfulBrain(choose="discovery-call-prep")
    container = await make_container(providers={"gemini": brain})
    await container.skills.set_enabled(tenant_id, user_id, "negotiation-plan", False)

    ctx = await start_run(container, tenant_id, user_id, turn_input("Prep me for my call with Acme"), user_message="Prep me for my call with Acme")
    await _done(container, ctx.session_id)

    first, second = [task for task in brain.tasks if task.purpose == "plan"]
    assert INDEX_HEADER in first.system and "- discovery-call-prep: Discovery call prep. Use when" in first.system
    assert "negotiation-plan" not in first.system  # switched off for this rep
    [loaded] = [json.loads(m.content) for m in second.messages if m.role is Role.TOOL and m.name == SKILL_TOOL]
    assert loaded["outcome"] == "EXECUTED" and loaded["data"]["instructions"] == BUILTIN_BY_KEY["discovery-call-prep"].content.instructions
    assert "doesn't change your rules" in loaded["data"]["note"]
    assert (await container.sessions.get(ctx.session_id)).status == SessionStatus.DONE

    usage = await _usage(container, tenant_id, user_id, "discovery-call-prep")
    assert (usage.total, usage.auto, usage.picked) == (1, 1, 0)
    audits = await container.ledger.list_audit(tenant_id=tenant_id, session_id=ctx.session_id)
    assert [(audit.agent, audit.tool, audit.outcome) for audit in audits] == [("orchestrator", SKILL_TOOL, "EXECUTED")]

    # What the agent can't use it can't load: a switched-off skill, one that doesn't exist, another rep's private skill.
    colleague = uuid4()
    workspace_service.add(colleague, tenant_id)
    theirs = await container.skills.create(tenant_id, colleague, visibility="PRIVATE", **{**BODY, "name": "Colleague secret play"})
    session = await open_session(container, tenant_id, user_id)
    for slug, message in (("negotiation-plan", "switched off"), ("no-such-skill", "there is no skill"), (theirs.slug, "there is no skill")):
        refused = await container.gate.call_tool(session, "orchestrator", SKILL_TOOL, {"skill": slug}, call_id=f"x-{slug}")
        assert refused.outcome.value == "INVALID" and message in (refused.error or ""), (slug, refused.error)


async def test_a_skill_the_rep_picks_is_loaded_before_the_models_first_step(make_container, rsa_keys, tenant_id, user_id):
    brain = SkillfulBrain()  # never chooses a skill itself
    container = await make_container(providers={"gemini": brain})
    headers = _headers(rsa_keys, user_id, tenant_id)
    await container.skills.set_enabled(tenant_id, user_id, "objection-handling", False)

    async with _api(container) as client:
        started = await client.post(f"{API_PREFIX}/chat", json={"message": "Acme said we're too expensive", "skill": "meeting-follow-up"}, headers=headers)
        assert started.status_code == 202, started.text
        session_id = UUID(started.json()["session_id"])
        await _done(container, session_id)
        detail = (await client.get(f"{API_PREFIX}/sessions/{session_id}", headers=headers)).json()

        switched_off = await client.post(f"{API_PREFIX}/chat", json={"message": "Handle this", "skill": "objection-handling"}, headers=headers)
        assert switched_off.status_code == 400 and "switched off" in switched_off.text
        unknown = await client.post(f"{API_PREFIX}/chat", json={"message": "Handle this", "skill": "made-up"}, headers=headers)
        assert unknown.status_code == 404

    [plan] = [task for task in brain.tasks if task.purpose == "plan"]  # one model step: the playbook was already there
    [loaded] = [json.loads(m.content) for m in plan.messages if m.role is Role.TOOL and m.name == SKILL_TOOL]
    assert loaded["data"]["name"] == "Meeting follow-up"
    assert [item["kind"] for item in detail["transcript"]] == ["user", "tool_call", "tool_result", "assistant"]
    assert detail["transcript"][1]["tool"] == SKILL_TOOL and detail["transcript"][2]["summary"] == "Using skill: Meeting follow-up"
    assert detail["transcript"][3]["text"] == "Done following: Meeting follow-up"
    usage = await _usage(container, tenant_id, user_id, "meeting-follow-up")
    assert (usage.total, usage.picked, usage.auto) == (1, 1, 0)


async def test_a_skill_handed_to_a_sub_agent_is_loaded_in_its_own_conversation(make_container, tenant_id, user_id):
    brain = SkillfulBrain(delegate_with="competitive-positioning")
    container = await make_container(providers={"gemini": brain})

    ctx = await start_run(container, tenant_id, user_id, turn_input("How do we beat Globex at Acme?"), user_message="How do we beat Globex at Acme?")
    await _done(container, ctx.session_id)

    [research] = [task for task in brain.tasks if task.purpose == "subagent:research"]  # it answered at once, playbook in hand
    [loaded] = [json.loads(m.content) for m in research.messages if m.role is Role.TOOL and m.name == SKILL_TOOL]
    assert loaded["data"]["name"] == "Competitive positioning"
    history = (await container.runner.snapshot(context_for(await container.sessions.get(ctx.session_id)))).values["messages"]
    [result] = [json.loads(m["content"]) for m in history if m.get("role") == "tool" and m.get("name") == DELEGATE_TOOL]
    assert result["data"]["answer"] == "Brief written following: Competitive positioning"
    audits = await container.ledger.list_audit(tenant_id=tenant_id, session_id=ctx.session_id)
    assert {(audit.agent, audit.tool, audit.outcome) for audit in audits} == {("orchestrator", DELEGATE_TOOL, "EXECUTED"), ("research", SKILL_TOOL, "EXECUTED")}
    usage = await _usage(container, tenant_id, user_id, "competitive-positioning")
    assert (usage.total, usage.delegated) == (1, 1)

    await container.skills.set_enabled(tenant_id, user_id, "competitive-positioning", False)
    session = await open_session(container, tenant_id, user_id)
    refused = await container.gate.call_tool(
        session, "orchestrator", DELEGATE_TOOL, {"agent": "research", "task": "Work out how we beat Globex", "skill": "competitive-positioning"}, call_id="d1"
    )
    assert refused.outcome.value == "INVALID" and "switched off" in (refused.error or "")
