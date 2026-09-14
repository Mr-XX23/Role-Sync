"""Postgres access for the Super Admin Console: overrides, audit, prompt versions, model-call metering
and the platform-wide reads (sessions, usage, tool calls) that no tenant-scoped repository offers."""

from __future__ import annotations

import logging
from collections.abc import Collection
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.admin.guard import AdminActor
from app.admin.runtime import AdminSnapshot, SettingRecord
from app.core.enums import PendingActionStatus, SessionStatus
from app.core.errors import Conflict
from app.db.models import (
    AdminAuditRow,
    AdminSettingRow,
    AgentSession,
    AuditEntry,
    ModelCallRow,
    PendingAction,
    PromptVersionRow,
)

logger = logging.getLogger(__name__)

SETTING_KEYS = ("controls", "tools", "routes", "rates")


@dataclass(frozen=True, slots=True)
class UsageRow:
    day: str
    tenant_id: UUID | None
    user_id: UUID | None
    session_id: UUID | None
    purpose: str
    provider: str
    model: str
    calls: int
    input_tokens: int
    output_tokens: int


class AdminStore:
    def __init__(self, sessionmaker: async_sessionmaker[AsyncSession]) -> None:
        self._sm = sessionmaker

    # ------------------------------------------------------------------ overrides
    async def load_snapshot(self) -> AdminSnapshot:
        async with self._sm() as db:
            settings = (await db.scalars(select(AdminSettingRow))).all()
            latest = (
                await db.scalars(
                    select(PromptVersionRow)
                    .distinct(PromptVersionRow.agent)
                    .order_by(PromptVersionRow.agent, PromptVersionRow.version.desc())
                )
            ).all()
        snapshot = AdminSnapshot(prompts={row.agent: (row.mode, row.instructions) for row in latest})
        for row in settings:
            if row.key in SETTING_KEYS:
                setattr(snapshot, row.key, SettingRecord(row.value, row.version, row.updated_at, row.updated_by_email))
        return snapshot

    async def save_setting(self, key: str, value: dict[str, Any], actor: AdminActor) -> SettingRecord:
        stmt = (
            insert(AdminSettingRow)
            .values(key=key, value=value, version=1, updated_by=actor.user_id, updated_by_email=actor.email)
            .on_conflict_do_update(
                index_elements=[AdminSettingRow.key],
                set_={
                    "value": value,
                    "version": AdminSettingRow.version + 1,
                    "updated_by": actor.user_id,
                    "updated_by_email": actor.email,
                    "updated_at": func.now(),
                },
            )
            .returning(AdminSettingRow)
        )
        async with self._sm.begin() as db:
            row = (await db.scalars(stmt)).one()
            return SettingRecord(row.value, row.version, row.updated_at, row.updated_by_email)

    # ------------------------------------------------------------------ audit
    async def audit(
        self,
        actor: AdminActor,
        *,
        action: str,
        target_type: str,
        summary: str,
        target_id: str | None = None,
        target_label: str | None = None,
    ) -> None:
        async with self._sm.begin() as db:
            db.add(
                AdminAuditRow(
                    actor_user_id=actor.user_id,
                    actor_email=actor.email,
                    action=action,
                    target_type=target_type,
                    target_id=target_id,
                    target_label=target_label,
                    summary=summary[:1000],
                )
            )

    async def list_audit(self, limit: int) -> list[AdminAuditRow]:
        async with self._sm() as db:
            rows = await db.scalars(select(AdminAuditRow).order_by(AdminAuditRow.created_at.desc()).limit(limit))
            return list(rows.all())

    # ------------------------------------------------------------------ prompts
    async def prompt_versions(self) -> dict[str, list[PromptVersionRow]]:
        async with self._sm() as db:
            rows = await db.scalars(select(PromptVersionRow).order_by(PromptVersionRow.agent, PromptVersionRow.version.desc()))
        grouped: dict[str, list[PromptVersionRow]] = {}
        for row in rows.all():
            grouped.setdefault(row.agent, []).append(row)
        return grouped

    async def prompt_version(self, agent: str, version: int) -> PromptVersionRow | None:
        async with self._sm() as db:
            return await db.scalar(
                select(PromptVersionRow).where(PromptVersionRow.agent == agent, PromptVersionRow.version == version)
            )

    async def publish_prompt(
        self, agent: str, *, mode: str, instructions: str, note: str | None, actor: AdminActor
    ) -> PromptVersionRow:
        try:
            async with self._sm.begin() as db:
                current = await db.scalar(select(func.max(PromptVersionRow.version)).where(PromptVersionRow.agent == agent))
                row = PromptVersionRow(
                    agent=agent,
                    version=int(current or 0) + 1,
                    mode=mode,
                    instructions=instructions,
                    note=note,
                    created_by=actor.user_id,
                    created_by_email=actor.email,
                )
                db.add(row)
            return row
        except IntegrityError as exc:
            raise Conflict("someone published this prompt at the same moment; reload and try again") from exc

    # ------------------------------------------------------------------ metering
    async def record_model_call(
        self,
        *,
        tenant_id: UUID | None,
        user_id: UUID | None,
        session_id: UUID | None,
        purpose: str,
        provider: str,
        model: str,
        input_tokens: int,
        output_tokens: int,
        duration_ms: int | None,
    ) -> None:
        async with self._sm.begin() as db:
            db.add(
                ModelCallRow(
                    tenant_id=tenant_id,
                    user_id=user_id,
                    session_id=session_id,
                    purpose=purpose[:200],
                    provider=provider,
                    model=model[:300],
                    input_tokens=max(0, input_tokens),
                    output_tokens=max(0, output_tokens),
                    duration_ms=duration_ms,
                )
            )

    async def usage_rows(self, since: datetime) -> list[UsageRow]:
        day = func.to_char(func.timezone("UTC", ModelCallRow.at), "YYYY-MM-DD")
        stmt = (
            select(
                day,
                ModelCallRow.tenant_id,
                ModelCallRow.user_id,
                ModelCallRow.session_id,
                ModelCallRow.purpose,
                ModelCallRow.provider,
                ModelCallRow.model,
                func.count(),
                func.coalesce(func.sum(ModelCallRow.input_tokens), 0),
                func.coalesce(func.sum(ModelCallRow.output_tokens), 0),
            )
            .where(ModelCallRow.at >= since)
            .group_by(
                day,
                ModelCallRow.tenant_id,
                ModelCallRow.user_id,
                ModelCallRow.session_id,
                ModelCallRow.purpose,
                ModelCallRow.provider,
                ModelCallRow.model,
            )
        )
        async with self._sm() as db:
            result = await db.execute(stmt)
            return [UsageRow(*(row[:7]), int(row[7]), int(row[8]), int(row[9])) for row in result.all()]

    async def session_usage(self, session_ids: Collection[UUID]) -> dict[UUID, list[tuple[str, str, int, int, int]]]:
        """Per session: (provider, model, calls, input tokens, output tokens)."""
        if not session_ids:
            return {}
        stmt = (
            select(
                ModelCallRow.session_id,
                ModelCallRow.provider,
                ModelCallRow.model,
                func.count(),
                func.coalesce(func.sum(ModelCallRow.input_tokens), 0),
                func.coalesce(func.sum(ModelCallRow.output_tokens), 0),
            )
            .where(ModelCallRow.session_id.in_(list(session_ids)))
            .group_by(ModelCallRow.session_id, ModelCallRow.provider, ModelCallRow.model)
        )
        grouped: dict[UUID, list[tuple[str, str, int, int, int]]] = {}
        async with self._sm() as db:
            for sid, provider, model, calls, tokens_in, tokens_out in (await db.execute(stmt)).all():
                grouped.setdefault(sid, []).append((provider, model, int(calls), int(tokens_in), int(tokens_out)))
        return grouped

    # ------------------------------------------------------------------ tool calls
    async def tool_outcomes(self, since: datetime) -> list[tuple[str, str, int]]:
        stmt = (
            select(AuditEntry.tool, AuditEntry.outcome, func.count())
            .where(AuditEntry.at >= since)
            .group_by(AuditEntry.tool, AuditEntry.outcome)
        )
        async with self._sm() as db:
            return [(tool, outcome, int(count)) for tool, outcome, count in (await db.execute(stmt)).all()]

    async def session_tool_calls(self, session_ids: Collection[UUID]) -> dict[UUID, int]:
        if not session_ids:
            return {}
        stmt = (
            select(AuditEntry.session_id, func.count())
            .where(AuditEntry.session_id.in_(list(session_ids)))
            .group_by(AuditEntry.session_id)
        )
        async with self._sm() as db:
            return {sid: int(count) for sid, count in (await db.execute(stmt)).all()}

    # ------------------------------------------------------------------ sessions
    async def sessions_started(self, since: datetime) -> list[tuple[str, UUID, UUID, UUID]]:
        """(UTC day, tenant, user, session) of every session started since."""
        day = func.to_char(func.timezone("UTC", AgentSession.started_at), "YYYY-MM-DD")
        stmt = select(day, AgentSession.tenant_id, AgentSession.user_id, AgentSession.id).where(AgentSession.started_at >= since)
        async with self._sm() as db:
            return [(d, t, u, i) for d, t, u, i in (await db.execute(stmt)).all()]

    async def status_counts(self) -> dict[str, int]:
        stmt = (
            select(AgentSession.status, func.count())
            .where(AgentSession.status.in_([SessionStatus.RUNNING, SessionStatus.AWAITING_APPROVAL]))
            .group_by(AgentSession.status)
        )
        async with self._sm() as db:
            return {status: int(count) for status, count in (await db.execute(stmt)).all()}

    async def list_sessions(self, status: SessionStatus | None, limit: int) -> list[AgentSession]:
        stmt = select(AgentSession)
        if status is not None:
            stmt = stmt.where(AgentSession.status == status)
        async with self._sm() as db:
            rows = await db.scalars(stmt.order_by(AgentSession.updated_at.desc()).limit(limit))
            return list(rows.all())

    async def get_session(self, session_id: UUID) -> AgentSession | None:
        async with self._sm() as db:
            return await db.get(AgentSession, session_id)

    async def expire_session_approvals(self, session_id: UUID, actor: AdminActor) -> list[PendingAction]:
        stmt = (
            update(PendingAction)
            .where(PendingAction.session_id == session_id, PendingAction.status == PendingActionStatus.PENDING)
            .values(
                status=PendingActionStatus.EXPIRED,
                resolved_at=func.now(),
                resolved_by=actor.user_id,
                decision_note="stopped by a platform administrator",
            )
            .returning(PendingAction)
        )
        async with self._sm.begin() as db:
            return list((await db.scalars(stmt)).all())
