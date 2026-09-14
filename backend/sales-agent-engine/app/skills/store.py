"""Skills in Postgres: custom skills and customized built-ins, their versions, on/off switches and usage.

Every save writes the skill's new content and a ``skill_version`` row in one transaction, and only
if the skill is still at the version the editor started from, so two people editing the same skill
can't silently overwrite each other.
"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID, uuid4

from sqlalchemy import and_, func, or_, select, text, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.enums import SkillUse, SkillVisibility
from app.db.models import SkillRow, SkillSettingRow, SkillUsageRow, SkillVersionRow
from app.skills.model import SkillContent, SkillUsage, slugify

_SLUG_ATTEMPTS = 50


class StaleSkill(Exception):
    """The skill changed (or was archived) since the editor loaded it."""


class SlugTaken(Exception):
    """A built-in customization already exists (only one per built-in)."""


@dataclass(frozen=True, slots=True)
class SkillSwitches:
    workspace: dict[str, bool]  # skill ref → an admin's switch for everyone
    personal: dict[str, bool]  # skill ref → this rep's own switch


class SkillStore:
    def __init__(self, sessionmaker: async_sessionmaker[AsyncSession]) -> None:
        self._sm = sessionmaker

    # ------------------------------------------------------------------ reads
    async def visible_rows(self, *, tenant_id: UUID, user_id: UUID, archived: bool = False) -> list[SkillRow]:
        """The workspace's skills and customizations plus the rep's own private skills (active, or archived)."""
        state = SkillRow.archived_at.is_not(None) if archived else SkillRow.archived_at.is_(None)
        async with self._sm() as db:
            rows = await db.scalars(
                select(SkillRow)
                .where(
                    SkillRow.tenant_id == tenant_id,
                    state,
                    or_(
                        SkillRow.visibility == SkillVisibility.WORKSPACE,
                        and_(SkillRow.visibility == SkillVisibility.PRIVATE, SkillRow.owner_id == user_id),
                    ),
                )
                .order_by(SkillRow.name)
            )
            return list(rows.all())

    async def get(self, *, tenant_id: UUID, skill_id: UUID) -> SkillRow | None:
        async with self._sm() as db:
            return await db.scalar(select(SkillRow).where(SkillRow.tenant_id == tenant_id, SkillRow.id == skill_id))

    async def customization(self, *, tenant_id: UUID, builtin_key: str) -> SkillRow | None:
        async with self._sm() as db:
            return await db.scalar(
                select(SkillRow).where(
                    SkillRow.tenant_id == tenant_id, SkillRow.builtin_key == builtin_key, SkillRow.archived_at.is_(None)
                )
            )

    async def count_active(self, *, tenant_id: UUID, visibility: SkillVisibility, owner_id: UUID | None = None) -> int:
        conditions = [SkillRow.tenant_id == tenant_id, SkillRow.visibility == visibility, SkillRow.archived_at.is_(None)]
        conditions.append(SkillRow.builtin_key.is_(None))
        if owner_id is not None:
            conditions.append(SkillRow.owner_id == owner_id)
        async with self._sm() as db:
            return int(await db.scalar(select(func.count()).select_from(SkillRow).where(*conditions)) or 0)

    async def versions(self, *, tenant_id: UUID, skill_id: UUID) -> list[SkillVersionRow]:
        async with self._sm() as db:
            rows = await db.scalars(
                select(SkillVersionRow)
                .where(SkillVersionRow.tenant_id == tenant_id, SkillVersionRow.skill_id == skill_id)
                .order_by(SkillVersionRow.version.desc())
            )
            return list(rows.all())

    async def version(self, *, tenant_id: UUID, skill_id: UUID, version: int) -> SkillVersionRow | None:
        async with self._sm() as db:
            return await db.scalar(
                select(SkillVersionRow).where(
                    SkillVersionRow.tenant_id == tenant_id, SkillVersionRow.skill_id == skill_id, SkillVersionRow.version == version
                )
            )

    # ------------------------------------------------------------------ writes
    async def create(
        self,
        *,
        tenant_id: UUID,
        user_id: UUID,
        visibility: SkillVisibility,
        content: SkillContent,
        note: str | None,
        builtin_key: str | None = None,
        owner_id: UUID | None = None,
    ) -> SkillRow:
        """A new skill at version 1. Its slug comes from its name, with a number added if another active
        skill of the workspace has it (a customized built-in keeps the built-in's key)."""
        base = builtin_key or slugify(content.name)
        for attempt in range(_SLUG_ATTEMPTS):
            slug = base if attempt == 0 else f"{base[: 60 - len(str(attempt + 1)) - 1]}-{attempt + 1}"
            if builtin_key is not None and attempt > 0:
                raise SlugTaken(builtin_key)
            row = SkillRow(
                id=uuid4(),
                tenant_id=tenant_id,
                slug=slug,
                visibility=visibility,
                owner_id=owner_id,
                builtin_key=builtin_key,
                name=content.name,
                description=content.description,
                instructions=content.instructions,
                category=content.category,
                tools=list(content.tools),
                version=1,
                created_by=user_id,
                updated_by=user_id,
            )
            try:
                async with self._sm.begin() as db:
                    db.add(row)
                    await db.flush()
                    db.add(_version_row(row, content, 1, user_id, note))
            except IntegrityError as exc:
                if "uq_skill_active_slug" in str(exc.orig):
                    continue
                raise
            return row
        raise SlugTaken(base)

    async def update(
        self,
        *,
        tenant_id: UUID,
        skill_id: UUID,
        expected_version: int,
        content: SkillContent,
        user_id: UUID,
        note: str | None,
    ) -> SkillRow:
        """Save new content as the next version, if the skill is still active at ``expected_version``."""
        async with self._sm.begin() as db:
            row = await db.scalar(
                update(SkillRow)
                .where(
                    SkillRow.tenant_id == tenant_id,
                    SkillRow.id == skill_id,
                    SkillRow.version == expected_version,
                    SkillRow.archived_at.is_(None),
                )
                .values(
                    name=content.name,
                    description=content.description,
                    instructions=content.instructions,
                    category=content.category,
                    tools=list(content.tools),
                    version=SkillRow.version + 1,
                    updated_by=user_id,
                    updated_at=func.now(),
                )
                .returning(SkillRow)
            )
            if row is None:
                raise StaleSkill(str(skill_id))
            db.add(_version_row(row, content, row.version, user_id, note))
            return row

    async def archive(self, *, tenant_id: UUID, skill_id: UUID, user_id: UUID) -> SkillRow | None:
        async with self._sm.begin() as db:
            return await db.scalar(
                update(SkillRow)
                .where(SkillRow.tenant_id == tenant_id, SkillRow.id == skill_id, SkillRow.archived_at.is_(None))
                .values(archived_at=func.now(), archived_by=user_id, updated_at=func.now())
                .returning(SkillRow)
            )

    async def unarchive(self, *, tenant_id: UUID, skill_id: UUID, user_id: UUID) -> SkillRow | None:
        """Bring an archived skill back. If its slug was taken meanwhile, it gets a numbered one."""
        current = await self.get(tenant_id=tenant_id, skill_id=skill_id)
        if current is None or current.archived_at is None:
            return None
        base = current.slug
        for attempt in range(_SLUG_ATTEMPTS):
            if current.builtin_key is not None and attempt > 0:
                raise SlugTaken(current.builtin_key)
            slug = base if attempt == 0 else f"{base[: 60 - len(str(attempt + 1)) - 1]}-{attempt + 1}"
            try:
                async with self._sm.begin() as db:
                    return await db.scalar(
                        update(SkillRow)
                        .where(SkillRow.tenant_id == tenant_id, SkillRow.id == skill_id, SkillRow.archived_at.is_not(None))
                        .values(archived_at=None, archived_by=None, slug=slug, updated_by=user_id, updated_at=func.now())
                        .returning(SkillRow)
                    )
            except IntegrityError as exc:
                if "uq_skill_active_slug" in str(exc.orig):
                    continue
                raise
        raise SlugTaken(base)

    # ------------------------------------------------------------------ switches
    async def settings(self, *, tenant_id: UUID, user_id: UUID) -> SkillSwitches:
        async with self._sm() as db:
            rows = await db.execute(
                select(SkillSettingRow.skill_ref, SkillSettingRow.user_id, SkillSettingRow.enabled).where(
                    SkillSettingRow.tenant_id == tenant_id,
                    or_(SkillSettingRow.user_id.is_(None), SkillSettingRow.user_id == user_id),
                )
            )
            workspace: dict[str, bool] = {}
            personal: dict[str, bool] = {}
            for ref, owner, enabled in rows.all():
                (workspace if owner is None else personal)[ref] = bool(enabled)
        return SkillSwitches(workspace=workspace, personal=personal)

    async def set_enabled(self, *, tenant_id: UUID, skill_ref: str, user_id: UUID | None, enabled: bool, by: UUID) -> None:
        """A rep's own switch (``user_id``), or the workspace switch for everyone (``user_id=None``)."""
        statement = insert(SkillSettingRow).values(
            id=uuid4(), tenant_id=tenant_id, skill_ref=skill_ref, user_id=user_id, enabled=enabled, updated_by=by
        )
        if user_id is None:
            statement = statement.on_conflict_do_update(
                index_elements=["tenant_id", "skill_ref"],
                index_where=text("user_id IS NULL"),
                set_={"enabled": enabled, "updated_by": by, "updated_at": func.now()},
            )
        else:
            statement = statement.on_conflict_do_update(
                index_elements=["tenant_id", "skill_ref", "user_id"],
                index_where=text("user_id IS NOT NULL"),
                set_={"enabled": enabled, "updated_by": by, "updated_at": func.now()},
            )
        async with self._sm.begin() as db:
            await db.execute(statement)

    # ------------------------------------------------------------------ usage
    async def record_use(
        self, *, tenant_id: UUID, skill_ref: str, version: int | None, user_id: UUID, session_id: UUID | None, how: SkillUse
    ) -> None:
        async with self._sm.begin() as db:
            db.add(
                SkillUsageRow(
                    tenant_id=tenant_id, skill_ref=skill_ref, skill_version=version, user_id=user_id, session_id=session_id, how=how
                )
            )

    async def usage(self, *, tenant_id: UUID, user_id: UUID) -> dict[str, SkillUsage]:
        """Per skill ref: uses by everyone in the workspace and by this rep, how, and the latest one."""
        async with self._sm() as db:
            rows = await db.execute(
                select(
                    SkillUsageRow.skill_ref,
                    func.count(),
                    func.count().filter(SkillUsageRow.user_id == user_id),
                    func.count().filter(SkillUsageRow.how == SkillUse.AUTO),
                    func.count().filter(SkillUsageRow.how == SkillUse.PICKED),
                    func.count().filter(SkillUsageRow.how == SkillUse.DELEGATED),
                    func.max(SkillUsageRow.used_at),
                )
                .where(SkillUsageRow.tenant_id == tenant_id)
                .group_by(SkillUsageRow.skill_ref)
            )
            return {
                ref: SkillUsage(total=total, mine=mine, auto=auto, picked=picked, delegated=delegated, last_used_at=last)
                for ref, total, mine, auto, picked, delegated, last in rows.all()
            }


def _version_row(row: SkillRow, content: SkillContent, version: int, user_id: UUID, note: str | None) -> SkillVersionRow:
    return SkillVersionRow(
        skill_id=row.id,
        tenant_id=row.tenant_id,
        version=version,
        name=content.name,
        description=content.description,
        instructions=content.instructions,
        category=content.category,
        tools=list(content.tools),
        note=note,
        edited_by=user_id,
    )
