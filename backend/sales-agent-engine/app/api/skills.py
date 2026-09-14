"""Skills: list, write, switch on or off, version history, SKILL.md import and export, AI drafts.

Who may do what is decided in ``app/skills/service.py``: everyone sees the built-ins and the
workspace's skills, owners and admins change those, members and above write private skills.
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Path, Response, status
from pydantic import BaseModel, ConfigDict, Field

from app.api.deps import ContainerDep, TenantDep
from app.container import Container
from app.core.context import TenantContext
from app.core.enums import SkillCategory, SkillVisibility
from app.skills.model import (
    DESCRIPTION_CHARS,
    INSTRUCTIONS_CHARS,
    MAX_ENABLED,
    MAX_PRIVATE_SKILLS,
    MAX_WORKSPACE_SKILLS,
    NAME_CHARS,
    TOOL_APPS,
    ParsedSkill,
    Skill,
    SkillSource,
)
from app.skills.service import ADMIN_ROLES, SkillEntry, SkillVersionInfo
from app.skills.skillmd import MAX_FILE_BYTES

router = APIRouter(tags=["skills"])

SkillRef = Annotated[str, Path(min_length=2, max_length=100, pattern=r"^[A-Za-z0-9][A-Za-z0-9-]*$")]


class _Body(BaseModel):
    model_config = ConfigDict(extra="forbid")


class SkillUsageView(BaseModel):
    total: int
    mine: int
    auto: int
    picked: int
    delegated: int
    last_used_at: datetime | None


class SkillView(BaseModel):
    ref: str  # a built-in's key or the skill id: what every other call takes
    slug: str  # what the agent calls it
    name: str
    description: str
    category: SkillCategory
    tools: list[str]
    apps: list[str]  # connected apps its tools need (Gmail, Slack, ...)
    source: SkillSource
    customized: bool  # a built-in this workspace changed
    version: int
    enabled: bool  # on for my agent
    my_switch: bool | None  # my own switch; None = never changed
    workspace_enabled: bool  # False when an admin switched it off for everyone
    editable: bool
    updated_at: datetime | None
    updated_by_me: bool
    usage: SkillUsageView


class SkillDetail(SkillView):
    instructions: str


class SkillLimits(BaseModel):
    enabled: int
    max_enabled: int
    workspace: int
    max_workspace: int
    private: int
    max_private: int


class SkillList(BaseModel):
    skills: list[SkillView]
    role: str | None
    can_create_private: bool
    can_manage_workspace: bool
    limits: SkillLimits


class SkillCreate(_Body):
    name: str = Field(min_length=NAME_CHARS[0], max_length=NAME_CHARS[1])
    description: str = Field(min_length=DESCRIPTION_CHARS[0], max_length=DESCRIPTION_CHARS[1])
    instructions: str = Field(min_length=INSTRUCTIONS_CHARS[0], max_length=INSTRUCTIONS_CHARS[1])
    category: SkillCategory = SkillCategory.OTHER
    tools: list[str] = Field(default_factory=list, max_length=20)
    visibility: SkillVisibility = SkillVisibility.PRIVATE
    note: str | None = Field(default=None, max_length=200, description="Why it was saved, e.g. 'Imported from SKILL.md'")


class SkillEdit(_Body):
    name: str = Field(min_length=NAME_CHARS[0], max_length=NAME_CHARS[1])
    description: str = Field(min_length=DESCRIPTION_CHARS[0], max_length=DESCRIPTION_CHARS[1])
    instructions: str = Field(min_length=INSTRUCTIONS_CHARS[0], max_length=INSTRUCTIONS_CHARS[1])
    category: SkillCategory
    tools: list[str] = Field(default_factory=list, max_length=20)
    expected_version: int = Field(ge=1, description="The version the edit started from; a newer one means someone else saved first")


class SwitchBody(_Body):
    enabled: bool


class RestoreBody(_Body):
    expected_version: int = Field(ge=1)


class ImportBody(_Body):
    content: str = Field(min_length=1, max_length=MAX_FILE_BYTES)


class DraftBody(_Body):
    idea: str = Field(min_length=10, max_length=500, description="What the skill should do, in a sentence or two")


class SkillDraft(BaseModel):
    """A skill read from a file or drafted by the model: for the editor, not saved yet."""

    name: str
    description: str
    instructions: str
    category: SkillCategory
    tools: list[str]
    warnings: list[str]


class SkillVersionView(BaseModel):
    version: int
    name: str
    description: str
    instructions: str
    category: SkillCategory
    tools: list[str]
    note: str | None
    edited_by_me: bool
    edited_at: datetime | None


class ArchivedSkill(BaseModel):
    id: UUID
    name: str
    description: str
    source: SkillSource
    version: int
    archived_at: datetime | None


class ToolView(BaseModel):
    name: str
    description: str
    app: str | None


# ----------------------------------------------------------------------------- routes (fixed paths first)


@router.get("/skills", response_model=SkillList)
async def list_skills(tenant: TenantDep, container: ContainerDep) -> SkillList:
    role = await container.workspaces.role_in(tenant.user_id, tenant.tenant_id)
    entries = await container.skills.entries(tenant.tenant_id, tenant.user_id)
    custom = [entry.skill for entry in entries if entry.skill.builtin_key is None]
    return SkillList(
        skills=[_view(entry, tenant, role) for entry in entries],
        role=role,
        can_create_private=role not in (None, "VIEWER"),
        can_manage_workspace=role in ADMIN_ROLES,
        limits=SkillLimits(
            enabled=sum(1 for entry in entries if entry.state.enabled),
            max_enabled=MAX_ENABLED,
            workspace=sum(1 for skill in custom if skill.source == SkillSource.WORKSPACE),
            max_workspace=MAX_WORKSPACE_SKILLS,
            private=sum(1 for skill in custom if skill.source == SkillSource.PRIVATE),
            max_private=MAX_PRIVATE_SKILLS,
        ),
    )


@router.get("/skills/tools", response_model=list[ToolView])
async def skill_tools(tenant: TenantDep, container: ContainerDep) -> list[ToolView]:
    """The tools a skill may name."""
    return [ToolView(name=name, description=summary, app=TOOL_APPS.get(name)) for name, summary in container.skills.tool_catalog()]


@router.get("/skills/archived", response_model=list[ArchivedSkill])
async def archived_skills(tenant: TenantDep, container: ContainerDep) -> list[ArchivedSkill]:
    return [
        ArchivedSkill(
            id=skill.id,
            name=skill.name,
            description=skill.content.description,
            source=skill.source,
            version=skill.version,
            archived_at=skill.archived_at,
        )
        for skill in await container.skills.archived(tenant.tenant_id, tenant.user_id)
        if skill.id is not None
    ]


@router.post("/skills", response_model=SkillDetail, status_code=status.HTTP_201_CREATED)
async def create_skill(body: SkillCreate, tenant: TenantDep, container: ContainerDep) -> SkillDetail:
    skill = await container.skills.create(
        tenant.tenant_id,
        tenant.user_id,
        visibility=body.visibility,
        name=body.name,
        description=body.description,
        instructions=body.instructions,
        category=body.category,
        tools=body.tools,
        note=body.note,
    )
    return await _detail(container, tenant, skill.ref)


@router.post("/skills/import/preview", response_model=SkillDraft)
async def preview_import(body: ImportBody, tenant: TenantDep, container: ContainerDep) -> SkillDraft:
    """Read a SKILL.md file into an editable skill (nothing is saved)."""
    return _draft(container.skills.preview_import(body.content))


@router.post("/skills/draft", response_model=SkillDraft)
async def draft_skill(body: DraftBody, tenant: TenantDep, container: ContainerDep) -> SkillDraft:
    """Have the model write a skill from an idea (nothing is saved)."""
    return _draft(await container.skills.draft(tenant.tenant_id, tenant.user_id, body.idea))


@router.post("/skills/archived/{skill_id}/restore", response_model=SkillDetail)
async def restore_archived(skill_id: UUID, tenant: TenantDep, container: ContainerDep) -> SkillDetail:
    skill = await container.skills.unarchive(tenant.tenant_id, tenant.user_id, skill_id)
    return await _detail(container, tenant, skill.ref)


@router.get("/skills/{ref}", response_model=SkillDetail)
async def get_skill(ref: SkillRef, tenant: TenantDep, container: ContainerDep) -> SkillDetail:
    return await _detail(container, tenant, ref)


@router.put("/skills/{ref}", response_model=SkillDetail)
async def edit_skill(ref: SkillRef, body: SkillEdit, tenant: TenantDep, container: ContainerDep) -> SkillDetail:
    skill = await container.skills.update(
        tenant.tenant_id,
        tenant.user_id,
        ref,
        expected_version=body.expected_version,
        name=body.name,
        description=body.description,
        instructions=body.instructions,
        category=body.category,
        tools=body.tools,
    )
    return await _detail(container, tenant, skill.ref)


@router.delete("/skills/{ref}", response_model=ArchivedSkill)
async def archive_skill(ref: SkillRef, tenant: TenantDep, container: ContainerDep) -> ArchivedSkill:
    """Archive a skill (it can be restored), or reset a customized built-in to the shipped version."""
    skill = await container.skills.archive(tenant.tenant_id, tenant.user_id, ref)
    assert skill.id is not None
    return ArchivedSkill(
        id=skill.id, name=skill.name, description=skill.content.description, source=skill.source, version=skill.version, archived_at=skill.archived_at
    )


@router.put("/skills/{ref}/enabled", response_model=SkillView)
async def switch_skill(ref: SkillRef, body: SwitchBody, tenant: TenantDep, container: ContainerDep) -> SkillView:
    """My own switch: whether my agent uses this skill."""
    entry = await container.skills.set_enabled(tenant.tenant_id, tenant.user_id, ref, body.enabled)
    return _view(entry, tenant, await container.workspaces.role_in(tenant.user_id, tenant.tenant_id))


@router.put("/skills/{ref}/workspace-enabled", response_model=SkillView)
async def switch_skill_for_everyone(ref: SkillRef, body: SwitchBody, tenant: TenantDep, container: ContainerDep) -> SkillView:
    """An owner's or admin's switch for everyone in the workspace."""
    entry = await container.skills.set_workspace_enabled(tenant.tenant_id, tenant.user_id, ref, body.enabled)
    return _view(entry, tenant, await container.workspaces.role_in(tenant.user_id, tenant.tenant_id))


@router.get("/skills/{ref}/versions", response_model=list[SkillVersionView])
async def skill_versions(ref: SkillRef, tenant: TenantDep, container: ContainerDep) -> list[SkillVersionView]:
    return [_version(item, tenant) for item in await container.skills.versions(tenant.tenant_id, tenant.user_id, ref)]


@router.post("/skills/{ref}/versions/{version}/restore", response_model=SkillDetail)
async def restore_version(
    ref: SkillRef, version: Annotated[int, Path(ge=1)], body: RestoreBody, tenant: TenantDep, container: ContainerDep
) -> SkillDetail:
    """Save an earlier version's content as the newest version."""
    skill = await container.skills.restore_version(
        tenant.tenant_id, tenant.user_id, ref, version=version, expected_version=body.expected_version
    )
    return await _detail(container, tenant, skill.ref)


@router.get("/skills/{ref}/export")
async def export_skill(ref: SkillRef, tenant: TenantDep, container: ContainerDep) -> Response:
    filename, text = await container.skills.export(tenant.tenant_id, tenant.user_id, ref)
    return Response(
        content=text,
        media_type="text/markdown; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ----------------------------------------------------------------------------- views


async def _detail(container: Container, tenant: TenantContext, ref: str) -> SkillDetail:
    entry = await container.skills.entry(tenant.tenant_id, tenant.user_id, ref)
    role = await container.workspaces.role_in(tenant.user_id, tenant.tenant_id)
    return SkillDetail(**_view(entry, tenant, role).model_dump(), instructions=entry.skill.content.instructions)


def _view(entry: SkillEntry, tenant: TenantContext, role: str | None) -> SkillView:
    skill = entry.skill
    usage = entry.usage
    return SkillView(
        ref=skill.ref,
        slug=skill.slug,
        name=skill.name,
        description=skill.content.description,
        category=skill.content.category,
        tools=list(skill.content.tools),
        apps=sorted({TOOL_APPS[tool] for tool in skill.content.tools if tool in TOOL_APPS}),
        source=skill.source,
        customized=skill.customized,
        version=skill.version,
        enabled=entry.state.enabled,
        my_switch=entry.state.personal,
        workspace_enabled=entry.state.workspace_enabled,
        editable=_editable(skill, tenant, role),
        updated_at=skill.updated_at,
        updated_by_me=skill.updated_by == tenant.user_id,
        usage=SkillUsageView(
            total=usage.total,
            mine=usage.mine,
            auto=usage.auto,
            picked=usage.picked,
            delegated=usage.delegated,
            last_used_at=usage.last_used_at,
        ),
    )


def _editable(skill: Skill, tenant: TenantContext, role: str | None) -> bool:
    if role in (None, "VIEWER"):
        return False
    if skill.source == SkillSource.PRIVATE:
        return skill.owner_id == tenant.user_id
    return role in ADMIN_ROLES


def _draft(parsed: ParsedSkill) -> SkillDraft:
    return SkillDraft(
        name=parsed.name,
        description=parsed.description,
        instructions=parsed.instructions,
        category=parsed.category,
        tools=list(parsed.tools),
        warnings=list(parsed.warnings),
    )


def _version(item: SkillVersionInfo, tenant: TenantContext) -> SkillVersionView:
    return SkillVersionView(
        version=item.version,
        name=item.content.name,
        description=item.content.description,
        instructions=item.content.instructions,
        category=item.content.category,
        tools=list(item.content.tools),
        note=item.note,
        edited_by_me=item.edited_by == tenant.user_id,
        edited_at=item.edited_at,
    )
