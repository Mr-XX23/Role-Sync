"""The rep's own profile and settings, over workspace-service.

Who the rep is (name, title, company, how they like to work) is in every prompt already (see the context
manager). ``get_my_profile`` shows all of it, contact details and links included, which stay out of prompts
until they are needed, and how many profile changes the rep has left.

Changing the profile is a gated write the rep approves. workspace-service allows 24 profile saves every 24
hours (and 3 photo changes, which only the Profile page makes), so the approval card says how many saves are
left, a change is refused before anyone is asked when none is, and one update carries every field the rep
asked to change. Undoing an update puts back the fields nobody changed since, and uses a save as well.
Settings (time zone, language, theme) have no limit.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable
from typing import Annotated, Any, Literal, TypeVar
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import Field, StringConstraints, field_validator

from app.core.context import AgentContext
from app.platform.workspace_client import ProfileClient, RepProfileClient, WorkspaceServiceError
from app.tools.adapters.common import clip, plural
from app.tools.registry import ToolDefinition
from app.tools.types import (
    SourceLink,
    ToolCategory,
    ToolFailed,
    ToolInput,
    ToolInputError,
    ToolInvocation,
    ToolKind,
    ToolOutcomeUnknown,
    ToolOutput,
    ToolScope,
    UndoInvocation,
    UndoPlan,
)

T = TypeVar("T")

PROFILE_PAGE = "/salesman/profile"

Name = Annotated[str, StringConstraints(strip_whitespace=True, max_length=50)]
Line = Annotated[str, StringConstraints(strip_whitespace=True, max_length=100)]
LongText = Annotated[str, StringConstraints(strip_whitespace=True, max_length=3_000)]
# The same checks as workspace-service's profile request; an empty string clears the field.
Link = Annotated[str, StringConstraints(strip_whitespace=True, max_length=500, pattern=r"^(https?://\S+)?$")]
Email = Annotated[
    str, StringConstraints(strip_whitespace=True, max_length=100, pattern=r"^([A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,})?$")
]
Phone = Annotated[str, StringConstraints(strip_whitespace=True, max_length=25, pattern=r"^(\+?[0-9\s()-]{7,25})?$")]
Tag = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=50, pattern=r"^[^,]+$")]
Tags = Annotated[list[Tag], Field(max_length=25)]
# The choices the Profile page offers.
CommunicationStyle = Literal["Strategic & Concise", "Technical & Analytical", "Comprehensive & Detailed", "Action-Oriented"]

# Each profile field the agent may change: (its name in workspace-service's profile, what the rep calls it).
_PROFILE_FIELDS: dict[str, tuple[str, str]] = {
    "first_name": ("firstName", "First name"),
    "last_name": ("lastName", "Last name"),
    "display_name": ("displayName", "Display name"),
    "job_title": ("jobTitle", "Job title"),
    "department": ("department", "Department"),
    "organization": ("organization", "Organization"),
    "location": ("location", "Location"),
    "secondary_email": ("secondaryEmail", "Secondary email"),
    "phone_number": ("phoneNumber", "Phone"),
    "bio": ("bio", "Bio"),
    "education": ("education", "Education"),
    "expertise": ("expertise", "Expertise"),
    "skills": ("skills", "Skills"),
    "interests": ("interests", "Interests"),
    "hobbies": ("hobbies", "Hobbies"),
    "communication_style": ("communicationStyle", "Communication style"),
    "ai_persona_context": ("aiPersonaContext", "Instructions for the agent"),
    "linkedin_url": ("linkedinUrl", "LinkedIn"),
    "github_url": ("githubUrl", "GitHub"),
    "website_url": ("websiteUrl", "Website"),
    "facebook_url": ("facebookUrl", "Facebook"),
    "x_url": ("xUrl", "X"),
    "instagram_url": ("instagramUrl", "Instagram"),
}
_TAG_FIELDS = frozenset({"expertise", "skills", "interests", "hobbies"})  # saved as comma-separated text
_SETTINGS: dict[str, tuple[str, str]] = {
    "time_zone": ("timezone", "Time zone"),
    "language": ("language", "Language"),
    "theme": ("theme", "Theme"),
}


class GetMyProfileArgs(ToolInput):
    pass


class UpdateMyProfileArgs(ToolInput):
    """Only the fields passed change. An empty string clears a field; a tag list replaces the whole list."""

    first_name: Name | None = None
    last_name: Name | None = None
    display_name: Line | None = Field(default=None, description="How their name is shown, e.g. 'Rohan Sharma'")
    job_title: Line | None = None
    department: Line | None = None
    organization: Line | None = Field(default=None, description="The company they work for")
    location: Line | None = None
    secondary_email: Email | None = Field(default=None, description="A second work email address")
    phone_number: Phone | None = None
    bio: LongText | None = None
    education: LongText | None = None
    expertise: Tags | None = Field(default=None, description="The whole list: include the current tags to keep")
    skills: Tags | None = Field(default=None, description="The whole list: include the current tags to keep")
    interests: Tags | None = Field(default=None, description="The whole list: include the current tags to keep")
    hobbies: Tags | None = Field(default=None, description="The whole list: include the current tags to keep")
    communication_style: CommunicationStyle | None = None
    ai_persona_context: Annotated[str, StringConstraints(strip_whitespace=True, max_length=5_000)] | None = Field(
        default=None, description="The rep's standing instructions for you, in their words (replaces what is there)"
    )
    linkedin_url: Link | None = None
    github_url: Link | None = None
    website_url: Link | None = None
    facebook_url: Link | None = None
    x_url: Link | None = None
    instagram_url: Link | None = None

    @field_validator("expertise", "skills", "interests", "hobbies")
    @classmethod
    def _without_repeats(cls, tags: list[str] | None) -> list[str] | None:
        if tags is None:
            return None
        seen: set[str] = set()
        kept = []
        for tag in tags:
            if tag.casefold() not in seen:
                seen.add(tag.casefold())
                kept.append(tag)
        return kept


class UpdateMyPreferencesArgs(ToolInput):
    time_zone: str | None = Field(default=None, max_length=64, description="An IANA name, e.g. 'Asia/Kathmandu'")
    language: Literal["en", "es", "fr", "de"] | None = Field(
        default=None, description="The app's language: en (English), es (Spanish), fr (French) or de (German)"
    )
    theme: Literal["light", "dark", "system"] | None = None

    @field_validator("time_zone")
    @classmethod
    def _known_time_zone(cls, value: str | None) -> str | None:
        if value is None:
            return None
        zone = value.strip()
        try:
            ZoneInfo(zone)
        except (ZoneInfoNotFoundError, ValueError) as exc:
            raise ValueError(f"'{zone}' is not a time zone: use an IANA name such as 'Europe/London'") from exc
        return zone


def profile_tools(profiles: ProfileClient, rep_profiles: RepProfileClient | None = None) -> list[ToolDefinition]:
    """``rep_profiles``: the cached profile the prompts are built from, refreshed after a change."""

    def changed(user_id: UUID) -> None:
        if rep_profiles is not None:
            rep_profiles.forget(user_id)

    # ------------------------------------------------------------------ read
    async def get_my_profile(invocation: ToolInvocation) -> ToolOutput:
        ctx = invocation.ctx
        profile, settings, limits = await asyncio.gather(
            _read(profiles.profile(ctx.user_id)), _optional(profiles.preferences(ctx.user_id)), _optional(profiles.limits(ctx.user_id))
        )
        saves, photos = _allowance(limits, "profile_saves"), _allowance(limits, "photo_changes")
        fields = {field: value for field in _PROFILE_FIELDS if (value := _stored(profile, field))}
        name = fields.get("display_name") or " ".join(fields.get(part, "") for part in ("first_name", "last_name")).strip()
        who = ", ".join(part for part in (name, fields.get("job_title")) if part) or "the rep"
        allowances = f": {_left(saves, 'profile save')}, {_left(photos, 'photo change')}" if saves and photos else ""
        return ToolOutput(
            data={
                "profile": fields | {"has_photo": bool(_text(profile.get("avatarUrl")))},
                "settings": _settings_view(settings),
                "profile_saves": saves,
                "photo_changes": photos,
            },
            summary=f"Profile of {who}{allowances}",
            sources=(SourceLink(title="Your profile", url=PROFILE_PAGE),),
        )

    # ------------------------------------------------------------------ profile
    async def profile_preview(ctx: AgentContext, args: ToolInput) -> dict[str, Any]:
        assert isinstance(args, UpdateMyProfileArgs)
        profile, limits = await asyncio.gather(_read(profiles.profile(ctx.user_id)), _optional(profiles.limits(ctx.user_id)))
        changes, _ = plan_profile_update(args, profile)
        if not changes:
            raise ToolInputError("nothing to change: the profile already has these values")
        saves = _allowance(limits, "profile_saves")
        if saves is not None and saves["remaining"] <= 0:
            raise ToolInputError(
                f"the rep has no profile saves left: all {saves['limit']} of this 24-hour window are used"
                f"{_until(saves)}. Don't propose the change now; tell the rep when they can save again."
            )
        return {"kind": "profile_update", "changes": changes, "profile_saves": saves}

    async def update_my_profile(invocation: ToolInvocation) -> ToolOutput:
        args = invocation.args
        assert isinstance(args, UpdateMyProfileArgs)
        ctx = invocation.ctx
        profile = await _read(profiles.profile(ctx.user_id))
        changes, fields = plan_profile_update(args, profile)
        if not changes:
            raise ToolInputError("nothing to change: the profile already has these values")
        try:
            await profiles.save_profile(ctx.user_id, fields)
        except WorkspaceServiceError as exc:
            if exc.maybe_applied:
                changed(ctx.user_id)
                raise ToolOutcomeUnknown(str(exc)) from exc
            raise ToolFailed(str(exc)) from exc  # e.g. 429: no save left; the message says when there is one again
        changed(ctx.user_id)
        saves = _allowance(await _optional(profiles.limits(ctx.user_id)), "profile_saves")
        left = f" {_left(saves, 'profile save')}." if saves else ""
        return ToolOutput(
            data={"changes": changes, "profile_saves": saves},
            summary="Profile updated: " + "; ".join(_describe(change) for change in changes) + "." + left,
            sources=(SourceLink(title="Your profile", url=PROFILE_PAGE),),
            undo=UndoPlan(
                args={
                    "restore": {change["field"]: change["before"] for change in changes},
                    "applied": {change["field"]: change["after"] for change in changes},
                },
                label="Put back the previous profile values (uses a profile save)",
            ),
        )

    async def restore_profile(invocation: UndoInvocation) -> str:
        ctx = invocation.ctx
        restore = {field: value for field, value in dict(invocation.args.get("restore") or {}).items() if field in _PROFILE_FIELDS}
        applied = dict(invocation.args.get("applied") or {})
        profile = await _read(profiles.profile(ctx.user_id))
        current = {field: _stored(profile, field) for field in restore}
        waiting = {field: value for field, value in restore.items() if not _same(field, current[field], value)}
        if not waiting:
            return "the profile already has its previous values"
        # Only fields still holding what the update set go back; later changes stay.
        restorable = {field: value for field, value in waiting.items() if _same(field, current[field], applied.get(field))}
        kept = ", ".join(_PROFILE_FIELDS[field][1] for field in waiting if field not in restorable)
        if not restorable:
            return f"nothing was put back: {kept} changed again since"
        try:
            await profiles.save_profile(ctx.user_id, {field: _wire(field, value) for field, value in restorable.items()})
        except WorkspaceServiceError as exc:
            # Repeating it is harmless, but not before a save is free again.
            raise ToolFailed(str(exc), retryable=exc.retryable and exc.status != 429) from exc
        changed(ctx.user_id)
        result = f"put back {plural(len(restorable), 'profile field')}"
        return f"{result}; kept later changes to {kept}" if kept else result

    # ------------------------------------------------------------------ settings
    async def preferences_preview(ctx: AgentContext, args: ToolInput) -> dict[str, Any]:
        assert isinstance(args, UpdateMyPreferencesArgs)
        changes, _ = plan_settings_update(args, await _read(profiles.preferences(ctx.user_id)))
        if not changes:
            raise ToolInputError("nothing to change: the settings already have these values")
        return {"kind": "preferences_update", "changes": changes}

    async def update_my_preferences(invocation: ToolInvocation) -> ToolOutput:
        args = invocation.args
        assert isinstance(args, UpdateMyPreferencesArgs)
        ctx = invocation.ctx
        changes, fields = plan_settings_update(args, await _read(profiles.preferences(ctx.user_id)))
        if not changes:
            raise ToolInputError("nothing to change: the settings already have these values")
        try:
            await profiles.save_preferences(ctx.user_id, fields)
        except WorkspaceServiceError as exc:
            if exc.maybe_applied:
                changed(ctx.user_id)
                raise ToolOutcomeUnknown(str(exc)) from exc
            raise ToolFailed(str(exc)) from exc
        changed(ctx.user_id)
        return ToolOutput(
            data={"changes": changes},
            summary="Settings changed: " + "; ".join(_describe(change) for change in changes),
            sources=(SourceLink(title="Your profile", url=PROFILE_PAGE),),
            undo=UndoPlan(
                args={
                    "restore": {change["field"]: change["before"] for change in changes if change["before"]},
                    "applied": {change["field"]: change["after"] for change in changes},
                },
                label="Put back the previous settings",
            ),
        )

    async def restore_preferences(invocation: UndoInvocation) -> str:
        ctx = invocation.ctx
        restore = {field: value for field, value in dict(invocation.args.get("restore") or {}).items() if field in _SETTINGS}
        applied = dict(invocation.args.get("applied") or {})
        settings = await _read(profiles.preferences(ctx.user_id))
        current = {field: _text(settings.get(_SETTINGS[field][0])) for field in restore}
        waiting = {field: value for field, value in restore.items() if current[field] != value}
        if not waiting:
            return "the settings already have their previous values"
        restorable = {field: value for field, value in waiting.items() if current[field] == applied.get(field)}
        kept = ", ".join(_SETTINGS[field][1] for field in waiting if field not in restorable)
        if not restorable:
            return f"nothing was put back: {kept} changed again since"
        try:
            await profiles.save_preferences(ctx.user_id, {_SETTINGS[field][0]: value for field, value in restorable.items()})
        except WorkspaceServiceError as exc:
            raise ToolFailed(str(exc), retryable=exc.retryable) from exc
        changed(ctx.user_id)
        result = f"put back {plural(len(restorable), 'setting')}"
        return f"{result}; kept later changes to {kept}" if kept else result

    return [
        ToolDefinition(
            name="get_my_profile",
            description=(
                "The rep's own profile (name, job title, company, contact details, links, bio, expertise and skills, "
                "their instructions for you) and settings (time zone, language, theme), with how many profile saves "
                "(24 every 24 hours) and photo changes (3 every 24 hours) they have left."
            ),
            kind=ToolKind.READ,
            scope=ToolScope.READ,
            category=ToolCategory.KNOWLEDGE,
            input_model=GetMyProfileArgs,
            handler=get_my_profile,
            timeout_seconds=20,
        ),
        ToolDefinition(
            name="update_my_profile",
            description=(
                "Change the rep's own profile when they ask. Only the fields you pass change: an empty string clears "
                "one, and a tag list (expertise, skills, interests, hobbies) replaces the whole list. Each update uses "
                "one of their 24 profile saves per 24 hours, so first check with get_my_profile that one is left, and "
                "put every requested change into one call. The rep approves it. The photo can't be changed here."
            ),
            kind=ToolKind.WRITE,
            scope=ToolScope.PROFILE,
            category=ToolCategory.ACTION,
            input_model=UpdateMyProfileArgs,
            handler=update_my_profile,
            timeout_seconds=30,
            preview=profile_preview,
            undo_handler=restore_profile,
        ),
        ToolDefinition(
            name="update_my_preferences",
            description=(
                "Change the rep's settings: time zone (an IANA name), language (en, es, fr or de) or theme (light, dark "
                "or system). There is no limit. The rep approves it."
            ),
            kind=ToolKind.WRITE,
            scope=ToolScope.PROFILE,
            category=ToolCategory.ACTION,
            input_model=UpdateMyPreferencesArgs,
            handler=update_my_preferences,
            timeout_seconds=30,
            preview=preferences_preview,
            undo_handler=restore_preferences,
        ),
    ]


def plan_profile_update(args: UpdateMyProfileArgs, profile: dict[str, Any]) -> tuple[list[dict[str, Any]], dict[str, str]]:
    """(the changes, as the rep sees them; the fields to save, as workspace-service takes them)."""
    changes: list[dict[str, Any]] = []
    fields: dict[str, str] = {}
    for field, value in args.model_dump(exclude_none=True).items():
        before = _stored(profile, field)
        if _same(field, before, value):
            continue
        changes.append({"field": field, "label": _PROFILE_FIELDS[field][1], "before": before, "after": value})
        fields[field] = _wire(field, value)
    return changes, fields


def plan_settings_update(args: UpdateMyPreferencesArgs, settings: dict[str, Any]) -> tuple[list[dict[str, Any]], dict[str, str]]:
    changes: list[dict[str, Any]] = []
    fields: dict[str, str] = {}
    for field, value in args.model_dump(exclude_none=True).items():
        key, label = _SETTINGS[field]
        before = _text(settings.get(key))
        if before == value:
            continue
        changes.append({"field": field, "label": label, "before": before, "after": value})
        fields[key] = value
    return changes, fields


async def _read(call: Awaitable[T]) -> T:
    try:
        return await call
    except WorkspaceServiceError as exc:
        raise ToolFailed(str(exc), retryable=exc.retryable) from exc


async def _optional(call: Awaitable[T]) -> T | None:
    """Worth showing when it can be read, and no reason to fail without it (workspace-service enforces the limits)."""
    try:
        return await call
    except WorkspaceServiceError:
        return None


def _stored(profile: dict[str, Any], field: str) -> Any:
    """A field's current value: a list for tags, text ("" when empty) for the rest."""
    raw = profile.get(_PROFILE_FIELDS[field][0])
    if field in _TAG_FIELDS:
        return [tag.strip() for tag in raw.split(",") if tag.strip()] if isinstance(raw, str) else []
    return _text(raw)


def _wire(field: str, value: Any) -> str:
    """A value as the Profile page saves it: tags joined with commas."""
    if field in _TAG_FIELDS:
        return ", ".join(value or [])
    return str(value or "")


def _same(field: str, left: Any, right: Any) -> bool:
    if field in _TAG_FIELDS:
        return list(left or []) == list(right or [])
    return _text(left) == _text(right)


def _text(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""


def _describe(change: dict[str, Any]) -> str:
    def show(value: Any) -> str:
        text = ", ".join(value) if isinstance(value, list) else str(value or "")
        return f"'{clip(text, 60)}'" if text else "(empty)"

    return f"{change['label']} {show(change['before'])} → {show(change['after'])}"


def _settings_view(settings: dict[str, Any] | None) -> dict[str, Any] | None:
    if settings is None:
        return None
    return {field: _text(settings.get(key)) or None for field, (key, _) in _SETTINGS.items()} | {
        "email_notifications": settings.get("notificationEmail"),
        "sms_notifications": settings.get("notificationSms"),
    }


def _allowance(limits: dict[str, Any] | None, key: str) -> dict[str, Any] | None:
    entry = limits.get(key) if isinstance(limits, dict) else None
    if not isinstance(entry, dict) or not isinstance(entry.get("remaining"), int) or not isinstance(entry.get("limit"), int):
        return None
    return {"limit": entry["limit"], "remaining": entry["remaining"], "resets_at": entry.get("resets_at")}


def _left(allowance: dict[str, Any] | None, noun: str) -> str:
    """'21 of 24 profile saves left', and when they are all back once none is."""
    if allowance is None:
        return ""
    text = f"{allowance['remaining']} of {plural(allowance['limit'], noun)} left"
    return text + _until(allowance) if allowance["remaining"] <= 0 else text


def _until(allowance: dict[str, Any]) -> str:
    return f" until {allowance['resets_at']}" if allowance.get("resets_at") else ""
