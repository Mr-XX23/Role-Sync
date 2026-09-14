"""Profile tools against a workspace-service double: what the agent reads about the rep, changes that
know how many profile saves are left, settings, and undo that keeps later edits."""

from __future__ import annotations

from typing import Any
from uuid import uuid4

import httpx
import pytest
from pydantic import ValidationError

from app.core.context import AgentContext, RunMode
from app.platform.workspace_client import ProfileClient, RepProfileClient
from app.tools.adapters.profile import profile_tools
from app.tools.registry import ToolDefinition
from app.tools.types import ToolFailed, ToolInputError, ToolInvocation, UndoInvocation
from tests.support import FakeWorkspaceService

WORKSPACE, REP = uuid4(), uuid4()
CTX = AgentContext(tenant_id=WORKSPACE, user_id=REP, session_id=uuid4(), mode=RunMode.INTERACTIVE, turn=1)

PROFILE = {
    "profileId": str(uuid4()), "authUserId": str(REP), "firstName": "Rohan", "lastName": "Sharma",
    "displayName": "Rohan Sharma", "jobTitle": "Account Executive", "organization": "Acme Corp",
    "phoneNumber": "+977 9800000000", "secondaryEmail": "rohan@acme.test", "skills": "Negotiation, SaaS",
    "linkedinUrl": "https://linkedin.com/in/rohan", "avatarUrl": "https://res.cloudinary.com/demo/rolesync/avatars/a.png",
    "bio": "", "dailyUpdateCount": 3,
}


def _setup(saves_used: int = 0) -> tuple[FakeWorkspaceService, RepProfileClient, dict[str, ToolDefinition]]:
    service = FakeWorkspaceService()
    service.profiles[REP] = dict(PROFILE)
    service.profile_saves[REP] = saves_used
    http = httpx.AsyncClient(transport=service.transport())
    cached = RepProfileClient(base_url="http://workspace.test", http=http)
    tools = profile_tools(ProfileClient(base_url="http://workspace.test", http=http), cached)
    return service, cached, {tool.name: tool for tool in tools}


async def _run(tool: ToolDefinition, arguments: dict[str, Any], *, call_id: str = "3-0-c1"):
    args = tool.input_model.model_validate(arguments)
    preview = await tool.build_preview(CTX, args)
    return preview, await tool.handler(ToolInvocation(CTX, "orchestrator", call_id, args))


def _saves(service: FakeWorkspaceService) -> list[Any]:
    return [body for method, route, body in service.profile_requests if method == "POST"]


async def test_the_agent_reads_the_whole_profile_with_the_settings_and_the_changes_left():
    service, _, tools = _setup(saves_used=3)
    tool = tools["get_my_profile"]

    output = await tool.handler(ToolInvocation(CTX, "orchestrator", "1-0-c1", tool.input_model.model_validate({})))

    profile = output.data["profile"]
    assert (profile["display_name"], profile["phone_number"], profile["secondary_email"]) == (
        "Rohan Sharma", "+977 9800000000", "rohan@acme.test"
    )
    assert profile["skills"] == ["Negotiation", "SaaS"] and profile["has_photo"] is True
    assert "bio" not in profile and "avatar_url" not in profile  # empty fields and the photo's address stay out
    assert output.data["settings"] == {
        "time_zone": "UTC", "language": "en", "theme": "dark", "email_notifications": True, "sms_notifications": True
    }
    assert output.data["profile_saves"] == {"limit": 24, "remaining": 21, "resets_at": "2026-09-15T10:00:00Z"}
    assert output.data["photo_changes"] == {"limit": 3, "remaining": 3, "resets_at": None}
    assert output.summary == "Profile of Rohan Sharma, Account Executive: 21 of 24 profile saves left, 3 of 3 photo changes left"
    assert output.sources[0].url == "/salesman/profile"
    assert _saves(service) == []  # reading uses no save


async def test_an_update_saves_only_what_changed_in_one_save_and_says_how_many_are_left():
    service, cached, tools = _setup(saves_used=3)
    assert (await cached.get(REP)).job_title == "Account Executive"  # what the prompts were built from

    preview, output = await _run(tools["update_my_profile"], {
        "job_title": "Senior Account Executive", "organization": "Acme Corp", "bio": "",
        "skills": ["Negotiation", "SaaS", "Fintech", "saas"],
    })

    assert preview == {
        "kind": "profile_update",
        "changes": [
            {"field": "job_title", "label": "Job title", "before": "Account Executive", "after": "Senior Account Executive"},
            {"field": "skills", "label": "Skills", "before": ["Negotiation", "SaaS"], "after": ["Negotiation", "SaaS", "Fintech"]},
        ],
        "profile_saves": {"limit": 24, "remaining": 21, "resets_at": "2026-09-15T10:00:00Z"},
    }
    assert _saves(service) == [{"job_title": "Senior Account Executive", "skills": "Negotiation, SaaS, Fintech"}]
    assert output.summary == (
        "Profile updated: Job title 'Account Executive' → 'Senior Account Executive'; "
        "Skills 'Negotiation, SaaS' → 'Negotiation, SaaS, Fintech'. 20 of 24 profile saves left."
    )
    assert output.undo is not None and "uses a profile save" in output.undo.label
    assert (await cached.get(REP)).job_title == "Senior Account Executive"  # the next prompt shows the change


async def test_with_no_save_left_the_change_is_refused_before_the_rep_is_asked():
    service, _, tools = _setup(saves_used=24)
    tool = tools["update_my_profile"]
    args = tool.input_model.model_validate({"job_title": "VP Sales"})

    with pytest.raises(ToolInputError, match="no profile saves left: all 24 of this 24-hour window are used until 2026-09-15T10:00:00Z"):
        await tool.build_preview(CTX, args)
    # If the last save goes between the approval and the save, workspace-service refuses and nothing changes.
    with pytest.raises(ToolFailed, match="429: Profile update limit reached"):
        await tool.handler(ToolInvocation(CTX, "orchestrator", "4-0-c1", args))
    assert service.profiles[REP]["jobTitle"] == "Account Executive"

    with pytest.raises(ToolInputError, match="nothing to change"):
        await tool.build_preview(CTX, tool.input_model.model_validate({"job_title": " Account Executive "}))


async def test_undo_puts_back_only_fields_nobody_changed_since_and_is_harmless_to_repeat():
    service, _, tools = _setup()
    tool = tools["update_my_profile"]
    _, output = await _run(tool, {"job_title": "Senior AE", "location": "Kathmandu", "skills": ["SaaS"]})
    service.profiles[REP]["location"] = "Pokhara"  # the rep changes it on the Profile page afterwards

    result = await tool.undo_handler(UndoInvocation(CTX, output.undo.args))

    profile = service.profiles[REP]
    assert (profile["jobTitle"], profile["skills"], profile["location"]) == ("Account Executive", "Negotiation, SaaS", "Pokhara")
    assert result == "put back 2 profile fields; kept later changes to Location"
    assert service.profile_saves[REP] == 2  # the update and its undo each used a save
    assert await tool.undo_handler(UndoInvocation(CTX, output.undo.args)) == "nothing was put back: Location changed again since"
    assert service.profile_saves[REP] == 2


async def test_an_undo_with_no_save_left_fails_and_is_not_retried():
    service, _, tools = _setup(saves_used=23)
    tool = tools["update_my_profile"]
    _, output = await _run(tool, {"job_title": "Senior AE"})
    assert output.summary.endswith("0 of 24 profile saves left until 2026-09-15T10:00:00Z.")

    with pytest.raises(ToolFailed, match="429") as failed:
        await tool.undo_handler(UndoInvocation(CTX, output.undo.args))

    assert failed.value.retryable is False
    assert service.profiles[REP]["jobTitle"] == "Senior AE"


def test_arguments_are_checked_as_workspace_service_checks_them():
    _, _, tools = _setup()
    profile_args = tools["update_my_profile"].input_model
    for wrong in (
        {"secondary_email": "not-an-email"}, {"phone_number": "call me"}, {"linkedin_url": "javascript:alert(1)"},
        {"communication_style": "Loud"}, {"skills": ["a, b"]}, {"skills": [f"tag {n}" for n in range(26)]},
        {"avatar_url": "https://example.com/me.png"},  # the photo is changed on the Profile page only
    ):
        with pytest.raises(ValidationError):
            profile_args.model_validate(wrong)
    cleared = profile_args.model_validate({"linkedin_url": "", "phone_number": ""})  # clearing is allowed
    assert (cleared.linkedin_url, cleared.phone_number) == ("", "")

    settings_args = tools["update_my_preferences"].input_model
    with pytest.raises(ValidationError, match="not a time zone"):
        settings_args.model_validate({"time_zone": "Mars/Olympus_Mons"})
    with pytest.raises(ValidationError):
        settings_args.model_validate({"language": "xx"})


async def test_settings_change_without_using_a_save_and_undo_puts_them_back():
    service, cached, tools = _setup(saves_used=24)  # no profile save left: settings don't need one
    tool = tools["update_my_preferences"]

    preview, output = await _run(tool, {"time_zone": "Asia/Kathmandu", "language": "es", "theme": "dark"})

    assert preview == {
        "kind": "preferences_update",
        "changes": [
            {"field": "time_zone", "label": "Time zone", "before": "UTC", "after": "Asia/Kathmandu"},
            {"field": "language", "label": "Language", "before": "en", "after": "es"},
        ],
    }
    assert (service.preferences[REP]["timezone"], service.preferences[REP]["language"]) == ("Asia/Kathmandu", "es")
    assert output.summary == "Settings changed: Time zone 'UTC' → 'Asia/Kathmandu'; Language 'en' → 'es'"
    assert (await cached.get(REP)).time_zone == "Asia/Kathmandu"

    assert await tool.undo_handler(UndoInvocation(CTX, output.undo.args)) == "put back 2 settings"
    assert (service.preferences[REP]["timezone"], service.preferences[REP]["language"]) == ("UTC", "en")
    assert await tool.undo_handler(UndoInvocation(CTX, output.undo.args)) == "the settings already have their previous values"


async def test_the_prompt_profile_reads_the_settings_but_not_the_time_zone_every_profile_starts_with():
    service, cached, _ = _setup()

    profile = await cached.get(REP)
    assert profile is not None and profile.name == "Rohan Sharma" and profile.language == "en"
    assert profile.time_zone is None  # UTC is only the default

    service.preferences[REP]["timezone"] = "America/New_York"
    assert (await cached.get(REP)).time_zone is None  # still the cached copy
    cached.forget(REP)
    assert (await cached.get(REP)).time_zone == "America/New_York"
