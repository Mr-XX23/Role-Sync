"""Super Admin Console: agent.admin_setting, agent.admin_audit, agent.prompt_version, agent.model_call.

Revision ID: 0007
Revises: 0006
Create Date: 2026-09-15 12:00:00
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = '0007'
down_revision: str | None = '0006'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table('admin_setting',
    sa.Column('key', sa.Text(), nullable=False),
    sa.Column('value', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('version', sa.Integer(), server_default='1', nullable=False),
    sa.Column('updated_by', sa.Uuid(), nullable=True),
    sa.Column('updated_by_email', sa.Text(), nullable=True),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.PrimaryKeyConstraint('key', name=op.f('pk_admin_setting')),
    schema='agent'
    )

    op.create_table('admin_audit',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('actor_user_id', sa.Uuid(), nullable=False),
    sa.Column('actor_email', sa.Text(), nullable=True),
    sa.Column('action', sa.Text(), nullable=False),
    sa.Column('target_type', sa.Text(), nullable=False),
    sa.Column('target_id', sa.Text(), nullable=True),
    sa.Column('target_label', sa.Text(), nullable=True),
    sa.Column('summary', sa.Text(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_admin_audit')),
    schema='agent'
    )
    op.create_index('ix_admin_audit_created_at', 'admin_audit', ['created_at'], unique=False, schema='agent')

    op.create_table('prompt_version',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('agent', sa.Text(), nullable=False),
    sa.Column('version', sa.Integer(), nullable=False),
    sa.Column('mode', sa.Text(), nullable=False),
    sa.Column('instructions', sa.Text(), nullable=False),
    sa.Column('note', sa.Text(), nullable=True),
    sa.Column('created_by', sa.Uuid(), nullable=False),
    sa.Column('created_by_email', sa.Text(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("mode IN ('APPEND', 'REPLACE')", name=op.f('ck_prompt_version_mode')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_prompt_version')),
    sa.UniqueConstraint('agent', 'version', name='uq_prompt_version_agent_version'),
    schema='agent'
    )

    op.create_table('model_call',
    sa.Column('id', sa.BigInteger(), sa.Identity(always=False), nullable=False),
    sa.Column('tenant_id', sa.Uuid(), nullable=True),
    sa.Column('user_id', sa.Uuid(), nullable=True),
    sa.Column('session_id', sa.Uuid(), nullable=True),
    sa.Column('purpose', sa.Text(), nullable=False),
    sa.Column('provider', sa.Text(), nullable=False),
    sa.Column('model', sa.Text(), nullable=False),
    sa.Column('input_tokens', sa.Integer(), server_default='0', nullable=False),
    sa.Column('output_tokens', sa.Integer(), server_default='0', nullable=False),
    sa.Column('duration_ms', sa.Integer(), nullable=True),
    sa.Column('at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_model_call')),
    schema='agent'
    )
    op.create_index('ix_model_call_at', 'model_call', ['at'], unique=False, schema='agent')
    op.create_index('ix_model_call_session_id', 'model_call', ['session_id'], unique=False, schema='agent')


def downgrade() -> None:
    op.drop_index('ix_model_call_session_id', table_name='model_call', schema='agent')
    op.drop_index('ix_model_call_at', table_name='model_call', schema='agent')
    op.drop_table('model_call', schema='agent')
    op.drop_table('prompt_version', schema='agent')
    op.drop_index('ix_admin_audit_created_at', table_name='admin_audit', schema='agent')
    op.drop_table('admin_audit', schema='agent')
    op.drop_table('admin_setting', schema='agent')
