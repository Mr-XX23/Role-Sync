"""agent.skill, agent.skill_version, agent.skill_setting, agent.skill_usage (skills the agent follows).

Revision ID: 0006
Revises: 0005
Create Date: 2026-09-14 12:00:00
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = '0006'
down_revision: str | None = '0005'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_CATEGORIES = "category IN ('PROSPECT', 'QUALIFY', 'ENGAGE', 'CLOSE', 'PIPELINE', 'OTHER')"


def upgrade() -> None:
    op.create_table('skill',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('tenant_id', sa.Uuid(), nullable=False),
    sa.Column('slug', sa.Text(), nullable=False),
    sa.Column('visibility', sa.Text(), nullable=False),
    sa.Column('owner_id', sa.Uuid(), nullable=True),
    sa.Column('builtin_key', sa.Text(), nullable=True),
    sa.Column('name', sa.Text(), nullable=False),
    sa.Column('description', sa.Text(), nullable=False),
    sa.Column('instructions', sa.Text(), nullable=False),
    sa.Column('category', sa.Text(), nullable=False),
    sa.Column('tools', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'[]'::jsonb"), nullable=False),
    sa.Column('version', sa.Integer(), server_default='1', nullable=False),
    sa.Column('created_by', sa.Uuid(), nullable=False),
    sa.Column('updated_by', sa.Uuid(), nullable=False),
    sa.Column('archived_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('archived_by', sa.Uuid(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("visibility IN ('WORKSPACE', 'PRIVATE')", name=op.f('ck_skill_visibility')),
    sa.CheckConstraint(_CATEGORIES, name=op.f('ck_skill_category')),
    sa.CheckConstraint("visibility <> 'PRIVATE' OR owner_id IS NOT NULL", name=op.f('ck_skill_private_owner')),
    sa.CheckConstraint("builtin_key IS NULL OR visibility = 'WORKSPACE'", name=op.f('ck_skill_builtin_shared')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_skill')),
    schema='agent'
    )
    op.create_index('uq_skill_active_slug', 'skill', ['tenant_id', 'slug'], unique=True, schema='agent', postgresql_where=sa.text('archived_at IS NULL'))
    op.create_index('ix_skill_tenant_visibility', 'skill', ['tenant_id', 'visibility'], unique=False, schema='agent')

    op.create_table('skill_version',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('skill_id', sa.Uuid(), nullable=False),
    sa.Column('tenant_id', sa.Uuid(), nullable=False),
    sa.Column('version', sa.Integer(), nullable=False),
    sa.Column('name', sa.Text(), nullable=False),
    sa.Column('description', sa.Text(), nullable=False),
    sa.Column('instructions', sa.Text(), nullable=False),
    sa.Column('category', sa.Text(), nullable=False),
    sa.Column('tools', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'[]'::jsonb"), nullable=False),
    sa.Column('note', sa.Text(), nullable=True),
    sa.Column('edited_by', sa.Uuid(), nullable=False),
    sa.Column('edited_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint(_CATEGORIES, name=op.f('ck_skill_version_category')),
    sa.ForeignKeyConstraint(['skill_id'], ['agent.skill.id'], name=op.f('fk_skill_version_skill_id_skill'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_skill_version')),
    sa.UniqueConstraint('skill_id', 'version', name='uq_skill_version_skill_version'),
    schema='agent'
    )

    op.create_table('skill_setting',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('tenant_id', sa.Uuid(), nullable=False),
    sa.Column('skill_ref', sa.Text(), nullable=False),
    sa.Column('user_id', sa.Uuid(), nullable=True),
    sa.Column('enabled', sa.Boolean(), nullable=False),
    sa.Column('updated_by', sa.Uuid(), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_skill_setting')),
    schema='agent'
    )
    op.create_index('uq_skill_setting_workspace', 'skill_setting', ['tenant_id', 'skill_ref'], unique=True, schema='agent', postgresql_where=sa.text('user_id IS NULL'))
    op.create_index('uq_skill_setting_user', 'skill_setting', ['tenant_id', 'skill_ref', 'user_id'], unique=True, schema='agent', postgresql_where=sa.text('user_id IS NOT NULL'))

    op.create_table('skill_usage',
    sa.Column('id', sa.BigInteger(), sa.Identity(always=False), nullable=False),
    sa.Column('tenant_id', sa.Uuid(), nullable=False),
    sa.Column('skill_ref', sa.Text(), nullable=False),
    sa.Column('skill_version', sa.Integer(), nullable=True),
    sa.Column('user_id', sa.Uuid(), nullable=False),
    sa.Column('session_id', sa.Uuid(), nullable=True),
    sa.Column('how', sa.Text(), nullable=False),
    sa.Column('used_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("how IN ('AUTO', 'PICKED', 'DELEGATED')", name=op.f('ck_skill_usage_how')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_skill_usage')),
    schema='agent'
    )
    op.create_index('ix_skill_usage_tenant_ref_used', 'skill_usage', ['tenant_id', 'skill_ref', 'used_at'], unique=False, schema='agent')


def downgrade() -> None:
    op.drop_index('ix_skill_usage_tenant_ref_used', table_name='skill_usage', schema='agent')
    op.drop_table('skill_usage', schema='agent')
    op.drop_index('uq_skill_setting_user', table_name='skill_setting', schema='agent')
    op.drop_index('uq_skill_setting_workspace', table_name='skill_setting', schema='agent')
    op.drop_table('skill_setting', schema='agent')
    op.drop_table('skill_version', schema='agent')
    op.drop_index('ix_skill_tenant_visibility', table_name='skill', schema='agent')
    op.drop_index('uq_skill_active_slug', table_name='skill', schema='agent')
    op.drop_table('skill', schema='agent')
