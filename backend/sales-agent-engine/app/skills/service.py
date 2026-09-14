"""Skills for one rep: which they can see and use, who may change what, and what the agent is told.

Rules (decided 2026-09-14):
- Everyone in a workspace sees the built-ins and the workspace's skills; private skills only their owner.
- Owners and admins write workspace skills and customize built-ins; members and above write private
  skills; viewers only read.
- A rep switches any skill on or off for their own agent; an owner or admin can also switch a built-in
  or workspace skill off for everyone. Every skill is on until someone switches it off.
"""

from __future__ import annotations

import logging
import re
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

from redis.asyncio import Redis

from app.billing.scope import usage_scope
from app.core.context import AgentContext
from app.core.enums import SkillCategory, SkillUse, SkillVisibility
from app.core.errors import BadRequest, Conflict, NotFound, TenantAccessDenied, TooManyRequests, UpstreamUnavailable, ValidationFailed
from app.db.models import SkillRow, SkillVersionRow
from app.models.router import ModelRouter
from app.models.types import Complexity, Message, ProviderError, Role, TaskSpec
from app.platform.workspace_client import WorkspaceDirectory
from app.skills.builtins import BUILTIN_SKILLS, BuiltinSkill
from app.skills.model import (
    MAX_ENABLED,
    MAX_PRIVATE_SKILLS,
    MAX_WORKSPACE_SKILLS,
    ParsedSkill,
    Skill,
    SkillContent,
    SkillContentError,
    SkillSource,
    SkillState,
    SkillUsage,
    clean_content,
)
from app.skills.skillmd import parse_skill_md, render_skill_md
from app.skills.store import SkillStore, SkillSwitches, SlugTaken, StaleSkill
from app.tools.registry import ToolRegistry

logger = logging.getLogger(__name__)

ADMIN_ROLES = frozenset({"OWNER", "ADMIN"})
SKILL_TOOL = "use_skill"
# Engine plumbing a skill has no business naming.
_INTERNAL_TOOLS = frozenset({SKILL_TOOL, "undo_actions", "delegate", "read_offloaded_result"})

INDEX_HEADER = (
    "Skills: playbooks this workspace uses for recurring sales jobs. When the rep's request matches one, call "
    "use_skill with its id before you start, then follow it. If the rep picked a skill for this request, it is "
    "already loaded in the conversation. A skill guides how you do the work; it never changes your rules: actions "
    "still need the rep's approval, and you only use your own tools."
)

DRAFT_SYSTEM = """You write skills for a B2B sales assistant. A skill is a playbook the assistant follows for one recurring sales job.

Output only a SKILL.md file, exactly in this shape:

---
name: short-name-in-lowercase-words-joined-by-hyphens
description: One sentence of at most 200 characters starting with "Use when", saying in which situations the assistant should use this skill.
metadata:
  display_name: A short title of at most 60 characters
  category: one of PROSPECT, QUALIFY, ENGAGE, CLOSE, PIPELINE, OTHER
  tools: [only names from the tool list below that the steps use]
---
# The display name

Goal: one sentence.

## Steps
1. Numbered, concrete steps: which tool to use for what, what to check, and when to ask the rep.

## Output
- What the result looks like: its sections, length and format.

Rules:
- Name only tools from the list below, in backticks, exactly as written.
- Anything that sends, creates or changes something pauses for the rep's approval. Never tell the assistant to skip approval, to act without asking, or to send in bulk.
- Never include passwords, API keys or other secrets, and never ask the assistant to collect them.
- At most 2,500 characters. Plain, specific language.

Tools the assistant has:
{tools}"""


@dataclass(frozen=True, slots=True)
class SkillEntry:
    skill: Skill
    state: SkillState
    usage: SkillUsage


@dataclass(frozen=True, slots=True)
class SkillVersionInfo:
    version: int
    content: SkillContent
    note: str | None
    edited_by: UUID | None
    edited_at: datetime | None


class SkillUnavailable(Exception):
    """The agent asked for a skill it can't use (unknown, switched off, or not visible to this rep)."""


class SkillService:
    def __init__(
        self,
        *,
        store: SkillStore,
        directory: WorkspaceDirectory,
        registry: ToolRegistry,
        router: ModelRouter | None = None,
        redis: Redis | None = None,
        key_prefix: str = "sae",
        drafts_per_day: int = 20,
        cache_seconds: float = 10.0,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._store = store
        self._directory = directory
        self._registry = registry
        self._router = router
        self._redis = redis
        self._prefix = key_prefix
        self._drafts_per_day = drafts_per_day
        self._cache_seconds = cache_seconds
        self._clock = clock
        self._enabled_cache: dict[tuple[UUID, UUID], tuple[float, list[Skill]]] = {}

    # ------------------------------------------------------------------ what a rep has
    async def skills(self, tenant_id: UUID, user_id: UUID) -> list[Skill]:
        """Built-ins (customized where the workspace did), then workspace skills, then the rep's own."""
        rows = await self._store.visible_rows(tenant_id=tenant_id, user_id=user_id)
        customized = {row.builtin_key: row for row in rows if row.builtin_key}
        result = [_from_row(customized[b.key]) if b.key in customized else _from_builtin(b) for b in BUILTIN_SKILLS]
        result += [_from_row(row) for row in rows if not row.builtin_key and row.visibility == SkillVisibility.WORKSPACE]
        result += [_from_row(row) for row in rows if not row.builtin_key and row.visibility == SkillVisibility.PRIVATE]
        return result

    async def entries(self, tenant_id: UUID, user_id: UUID) -> list[SkillEntry]:
        skills = await self.skills(tenant_id, user_id)
        settings = await self._store.settings(tenant_id=tenant_id, user_id=user_id)
        usage = await self._store.usage(tenant_id=tenant_id, user_id=user_id)
        return [SkillEntry(skill=skill, state=_state(skill, settings), usage=usage.get(skill.ref, SkillUsage())) for skill in skills]

    async def archived(self, tenant_id: UUID, user_id: UUID) -> list[Skill]:
        """Archived skills this rep could bring back: their own, and the workspace's if they are an admin."""
        role = await self._directory.role_in(user_id, tenant_id)
        rows = await self._store.visible_rows(tenant_id=tenant_id, user_id=user_id, archived=True)
        return [
            _from_row(row)
            for row in rows
            if row.visibility == SkillVisibility.PRIVATE or role in ADMIN_ROLES
        ]

    async def entry(self, tenant_id: UUID, user_id: UUID, ref: str) -> SkillEntry:
        for item in await self.entries(tenant_id, user_id):
            if item.skill.ref == ref:
                return item
        raise NotFound("that skill doesn't exist, or isn't visible to you")

    async def enabled(self, tenant_id: UUID, user_id: UUID) -> list[Skill]:
        """The skills switched on for this rep's agent (briefly cached: every planning step asks)."""
        key = (tenant_id, user_id)
        cached = self._enabled_cache.get(key)
        now = self._clock()
        if cached is not None and now - cached[0] < self._cache_seconds:
            return cached[1]
        skills = [item.skill for item in await self.entries(tenant_id, user_id) if item.state.enabled]
        self._enabled_cache[key] = (now, skills)
        return skills

    async def index_text(self, tenant_id: UUID, user_id: UUID) -> str:
        """The skills list in the agent's instructions (empty when none is switched on)."""
        try:
            skills = (await self.enabled(tenant_id, user_id))[:MAX_ENABLED]
        except Exception:
            logger.warning("could not load skills for the agent's instructions", exc_info=True)
            return ""
        if not skills:
            return ""
        lines = [f"- {skill.slug}: {skill.name}. {skill.content.description}" for skill in skills]
        return INDEX_HEADER + "\n" + "\n".join(lines)

    async def usable(self, tenant_id: UUID, user_id: UUID, slug: str) -> Skill:
        """The skill the agent asked for by id, if this rep's agent may use it now."""
        wanted = slug.strip().lower()
        for item in await self.entries(tenant_id, user_id):
            if item.skill.slug == wanted:
                if not item.state.enabled:
                    raise SkillUnavailable(f"the skill '{item.skill.name}' is switched off; carry on without it")
                return item.skill
        raise SkillUnavailable(f"there is no skill '{slug}'; use an id from the skills list in your instructions")

    async def pickable(self, tenant_id: UUID, user_id: UUID, ref: str) -> Skill:
        """A skill the rep picked in the chat, by its ref."""
        item = await self.entry(tenant_id, user_id, ref)
        if not item.state.enabled:
            raise BadRequest(f"'{item.skill.name}' is switched off; switch it on under Agent Skills to use it")
        return item.skill

    async def record_use(self, ctx: AgentContext, skill: Skill, how: SkillUse) -> None:
        try:
            await self._store.record_use(
                tenant_id=ctx.tenant_id, skill_ref=skill.ref, version=skill.version, user_id=ctx.user_id, session_id=ctx.session_id, how=how
            )
        except Exception:
            logger.warning("could not record a use of skill %s", skill.ref, exc_info=True)

    # ------------------------------------------------------------------ writing skills
    def tool_names(self) -> frozenset[str]:
        """Tools a skill may name: what this agent can call, minus engine plumbing."""
        return frozenset(definition.name for definition in self._registry.all() if definition.name not in _INTERNAL_TOOLS)

    def tool_catalog(self) -> list[tuple[str, str]]:
        """(name, first sentence of its description) of every tool a skill may name."""
        return sorted(
            (definition.name, _first_sentence(definition.description))
            for definition in self._registry.all()
            if definition.name not in _INTERNAL_TOOLS
        )

    async def create(
        self,
        tenant_id: UUID,
        user_id: UUID,
        *,
        visibility: SkillVisibility,
        name: str,
        description: str,
        instructions: str,
        category: str,
        tools: list[str],
        note: str | None = None,
    ) -> Skill:
        await self._require_writer(tenant_id, user_id, visibility)
        content = self._content(name, description, instructions, category, tools)
        if visibility == SkillVisibility.WORKSPACE:
            if await self._store.count_active(tenant_id=tenant_id, visibility=visibility) >= MAX_WORKSPACE_SKILLS:
                raise Conflict(f"a workspace can have up to {MAX_WORKSPACE_SKILLS} skills; archive one first")
        elif await self._store.count_active(tenant_id=tenant_id, visibility=visibility, owner_id=user_id) >= MAX_PRIVATE_SKILLS:
            raise Conflict(f"you can have up to {MAX_PRIVATE_SKILLS} private skills; archive one first")
        row = await self._store.create(
            tenant_id=tenant_id,
            user_id=user_id,
            visibility=visibility,
            content=content,
            note=note,
            owner_id=user_id,
        )
        self._forget(tenant_id)
        return _from_row(row)

    async def update(
        self,
        tenant_id: UUID,
        user_id: UUID,
        ref: str,
        *,
        expected_version: int,
        name: str,
        description: str,
        instructions: str,
        category: str,
        tools: list[str],
        note: str | None = None,
    ) -> Skill:
        skill = (await self.entry(tenant_id, user_id, ref)).skill
        await self._require_editor(tenant_id, user_id, skill)
        content = self._content(name, description, instructions, category, tools)
        if skill.version != expected_version:
            raise Conflict(f"'{skill.name}' was changed by someone else (now version {skill.version}); reload it and try again")
        if skill.source == SkillSource.BUILTIN and not skill.customized:
            try:
                row = await self._store.create(
                    tenant_id=tenant_id,
                    user_id=user_id,
                    visibility=SkillVisibility.WORKSPACE,
                    content=content,
                    note=note or f"Customized from the built-in skill (version {skill.version})",
                    builtin_key=skill.builtin_key,
                    owner_id=user_id,
                )
            except SlugTaken as exc:
                raise Conflict(f"'{skill.name}' was customized by someone else just now; reload it and try again") from exc
            self._forget(tenant_id)
            return _from_row(row)
        assert skill.id is not None
        try:
            row = await self._store.update(
                tenant_id=tenant_id, skill_id=skill.id, expected_version=expected_version, content=content, user_id=user_id, note=note
            )
        except StaleSkill as exc:
            raise Conflict(f"'{skill.name}' was changed by someone else; reload it and try again") from exc
        self._forget(tenant_id)
        return _from_row(row)

    async def archive(self, tenant_id: UUID, user_id: UUID, ref: str) -> Skill:
        """Archive a custom skill, or reset a customized built-in to the shipped version. Nothing is deleted."""
        skill = (await self.entry(tenant_id, user_id, ref)).skill
        if skill.source == SkillSource.BUILTIN and not skill.customized:
            raise BadRequest(f"'{skill.name}' is built in: switch it off, or customize it, instead")
        await self._require_editor(tenant_id, user_id, skill)
        assert skill.id is not None
        archived = await self._store.archive(tenant_id=tenant_id, skill_id=skill.id, user_id=user_id)
        if archived is None:
            raise NotFound("that skill was already archived")
        self._forget(tenant_id)
        return _from_row(archived)

    async def unarchive(self, tenant_id: UUID, user_id: UUID, skill_id: UUID) -> Skill:
        row = await self._store.get(tenant_id=tenant_id, skill_id=skill_id)
        if row is None or (row.visibility == SkillVisibility.PRIVATE and row.owner_id != user_id) or row.archived_at is None:
            raise NotFound("there is no archived skill with that id")
        skill = _from_row(row)
        await self._require_editor(tenant_id, user_id, skill)
        if row.visibility == SkillVisibility.WORKSPACE and row.builtin_key is None:
            if await self._store.count_active(tenant_id=tenant_id, visibility=SkillVisibility.WORKSPACE) >= MAX_WORKSPACE_SKILLS:
                raise Conflict(f"a workspace can have up to {MAX_WORKSPACE_SKILLS} skills; archive one first")
        elif row.visibility == SkillVisibility.PRIVATE:
            if await self._store.count_active(tenant_id=tenant_id, visibility=SkillVisibility.PRIVATE, owner_id=user_id) >= MAX_PRIVATE_SKILLS:
                raise Conflict(f"you can have up to {MAX_PRIVATE_SKILLS} private skills; archive one first")
        try:
            restored = await self._store.unarchive(tenant_id=tenant_id, skill_id=skill_id, user_id=user_id)
        except SlugTaken as exc:
            raise Conflict(f"'{row.name}' has been customized again since it was reset; archive that version first") from exc
        if restored is None:
            raise NotFound("there is no archived skill with that id")
        self._forget(tenant_id)
        return _from_row(restored)

    async def set_enabled(self, tenant_id: UUID, user_id: UUID, ref: str, enabled: bool) -> SkillEntry:
        """A rep's own switch for their agent."""
        entries = await self.entries(tenant_id, user_id)
        item = next((entry for entry in entries if entry.skill.ref == ref), None)
        if item is None:
            raise NotFound("that skill doesn't exist, or isn't visible to you")
        if enabled and not item.state.workspace_enabled:
            raise Conflict(f"a workspace admin switched '{item.skill.name}' off for everyone")
        if enabled and not item.state.enabled:
            switched_on = sum(1 for entry in entries if entry.state.enabled)
            if switched_on >= MAX_ENABLED:
                raise Conflict(f"up to {MAX_ENABLED} skills can be switched on at once; switch one off first")
        await self._store.set_enabled(tenant_id=tenant_id, skill_ref=ref, user_id=user_id, enabled=enabled, by=user_id)
        self._forget(tenant_id)
        return await self.entry(tenant_id, user_id, ref)

    async def set_workspace_enabled(self, tenant_id: UUID, user_id: UUID, ref: str, enabled: bool) -> SkillEntry:
        """An owner's or admin's switch for everyone in the workspace (built-in and workspace skills)."""
        item = await self.entry(tenant_id, user_id, ref)
        if item.skill.source == SkillSource.PRIVATE:
            raise BadRequest("a private skill is only ever switched by its owner")
        role = await self._directory.role_in(user_id, tenant_id)
        if role not in ADMIN_ROLES:
            raise TenantAccessDenied("only workspace owners and admins can switch a skill off for everyone")
        await self._store.set_enabled(tenant_id=tenant_id, skill_ref=ref, user_id=None, enabled=enabled, by=user_id)
        self._forget(tenant_id)
        return await self.entry(tenant_id, user_id, ref)

    async def versions(self, tenant_id: UUID, user_id: UUID, ref: str) -> list[SkillVersionInfo]:
        skill = (await self.entry(tenant_id, user_id, ref)).skill
        if skill.id is None:
            assert skill.builtin_key is not None
            return [SkillVersionInfo(version=skill.version, content=skill.content, note="Built in", edited_by=None, edited_at=None)]
        return [_version_info(row) for row in await self._store.versions(tenant_id=tenant_id, skill_id=skill.id)]

    async def restore_version(self, tenant_id: UUID, user_id: UUID, ref: str, *, version: int, expected_version: int) -> Skill:
        skill = (await self.entry(tenant_id, user_id, ref)).skill
        if skill.id is None:
            raise BadRequest(f"'{skill.name}' hasn't been changed, so there is no earlier version")
        old = await self._store.version(tenant_id=tenant_id, skill_id=skill.id, version=version)
        if old is None:
            raise NotFound(f"'{skill.name}' has no version {version}")
        return await self.update(
            tenant_id,
            user_id,
            ref,
            expected_version=expected_version,
            name=old.name,
            description=old.description,
            instructions=old.instructions,
            category=old.category,
            tools=[tool for tool in old.tools if tool in self.tool_names()],
            note=f"Restored from version {version}",
        )

    async def export(self, tenant_id: UUID, user_id: UUID, ref: str) -> tuple[str, str]:
        """(file name, SKILL.md text)."""
        skill = (await self.entry(tenant_id, user_id, ref)).skill
        return f"{skill.slug}-SKILL.md", render_skill_md(skill)

    def preview_import(self, text: str) -> ParsedSkill:
        try:
            return parse_skill_md(text, known_tools=self.tool_names())
        except SkillContentError as exc:
            raise ValidationFailed(str(exc)) from exc

    async def draft(self, tenant_id: UUID, user_id: UUID, idea: str) -> ParsedSkill:
        """A skill written by the model from a one-line idea, for the rep to edit. Nothing is saved."""
        role = await self._directory.role_in(user_id, tenant_id)
        if role is None or role == "VIEWER":
            raise TenantAccessDenied("viewers can't write skills")
        if self._router is None:
            raise UpstreamUnavailable("no model is configured to draft skills")
        await self._count_draft(user_id)
        tools = "\n".join(f"- {name}: {summary}" for name, summary in self.tool_catalog())
        task = TaskSpec(
            purpose="skill-draft",
            system=DRAFT_SYSTEM.format(tools=tools),
            messages=(Message(role=Role.USER, content=f"Write a skill for this: {idea.strip()}"),),
            complexity=Complexity.HIGH,
            temperature=0.4,
            max_output_tokens=3_000,
        )
        try:
            with usage_scope(tenant_id, user_id):  # not part of a run: the draft's model call is charged here
                completion = await self._router.complete(task)
        except ProviderError as exc:
            raise UpstreamUnavailable(f"the model couldn't draft the skill right now: {exc}") from exc
        try:
            return parse_skill_md(completion.message.content, known_tools=self.tool_names())
        except SkillContentError as exc:
            logger.warning("a drafted skill could not be read: %s", exc)
            raise UpstreamUnavailable("the draft came back in a shape that couldn't be read; try again") from exc

    # ------------------------------------------------------------------ helpers
    def _content(self, name: str, description: str, instructions: str, category: str, tools: list[str]) -> SkillContent:
        try:
            return clean_content(
                name=name, description=description, instructions=instructions, category=category, tools=tools, known_tools=self.tool_names()
            )
        except SkillContentError as exc:
            raise ValidationFailed(str(exc)) from exc

    async def _require_writer(self, tenant_id: UUID, user_id: UUID, visibility: SkillVisibility) -> str:
        role = await self._directory.role_in(user_id, tenant_id)
        if role is None:
            raise TenantAccessDenied("you are not a member of this workspace")
        if role == "VIEWER":
            raise TenantAccessDenied("viewers can't create or change skills")
        if visibility == SkillVisibility.WORKSPACE and role not in ADMIN_ROLES:
            raise TenantAccessDenied("only workspace owners and admins can write skills for the whole workspace")
        return role

    async def _require_editor(self, tenant_id: UUID, user_id: UUID, skill: Skill) -> None:
        if skill.source == SkillSource.PRIVATE:
            if skill.owner_id != user_id:
                raise NotFound("that skill doesn't exist, or isn't visible to you")
            await self._require_writer(tenant_id, user_id, SkillVisibility.PRIVATE)
            return
        await self._require_writer(tenant_id, user_id, SkillVisibility.WORKSPACE)

    async def _count_draft(self, user_id: UUID) -> None:
        if self._redis is None:
            return
        key = f"{self._prefix}:skill-drafts:{user_id}:{datetime.now(UTC).date().isoformat()}"
        count = int(await self._redis.incr(key))
        if count == 1:
            await self._redis.expire(key, 2 * 86_400)
        if count > self._drafts_per_day:
            raise TooManyRequests(f"you can draft up to {self._drafts_per_day} skills with AI a day; write this one yourself or try tomorrow")

    def _forget(self, tenant_id: UUID) -> None:
        for key in [key for key in self._enabled_cache if key[0] == tenant_id]:
            self._enabled_cache.pop(key, None)


def _from_builtin(builtin: BuiltinSkill) -> Skill:
    return Skill(
        ref=builtin.key,
        slug=builtin.key,
        source=SkillSource.BUILTIN,
        content=builtin.content,
        version=builtin.version,
        builtin_key=builtin.key,
    )


def _from_row(row: SkillRow) -> Skill:
    content = SkillContent(
        name=row.name,
        description=row.description,
        instructions=row.instructions,
        category=SkillCategory(row.category),
        tools=tuple(row.tools or ()),
    )
    if row.builtin_key:
        return Skill(
            ref=row.builtin_key,
            slug=row.slug,
            source=SkillSource.BUILTIN,
            content=content,
            version=row.version,
            id=row.id,
            builtin_key=row.builtin_key,
            owner_id=row.owner_id,
            updated_by=row.updated_by,
            updated_at=row.updated_at,
            archived_at=row.archived_at,
        )
    return Skill(
        ref=str(row.id),
        slug=row.slug,
        source=SkillSource(row.visibility),
        content=content,
        version=row.version,
        id=row.id,
        owner_id=row.owner_id,
        updated_by=row.updated_by,
        updated_at=row.updated_at,
        archived_at=row.archived_at,
    )


def _state(skill: Skill, switches: SkillSwitches) -> SkillState:
    workspace_enabled = True if skill.source == SkillSource.PRIVATE else switches.workspace.get(skill.ref, True)
    personal = switches.personal.get(skill.ref)
    return SkillState(enabled=workspace_enabled and (personal if personal is not None else True), personal=personal, workspace_enabled=workspace_enabled)


def _version_info(row: SkillVersionRow) -> SkillVersionInfo:
    return SkillVersionInfo(
        version=row.version,
        content=SkillContent(
            name=row.name,
            description=row.description,
            instructions=row.instructions,
            category=SkillCategory(row.category),
            tools=tuple(row.tools or ()),
        ),
        note=row.note,
        edited_by=row.edited_by,
        edited_at=row.edited_at,
    )


def _first_sentence(text: str, limit: int = 160) -> str:
    sentence = re.split(r"(?<=[.!?])\s", " ".join(text.split()), maxsplit=1)[0]
    return sentence if len(sentence) <= limit else sentence[: limit - 1].rstrip() + "…"
