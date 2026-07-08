"""voice infrastructure

Revision ID: 20260617_0005
Revises: 20260616_0004
Create Date: 2026-06-17
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20260617_0005"
down_revision: Union[str, None] = "20260616_0004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "voice_sessions",
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("workspace_id", sa.String(length=36), nullable=False),
        sa.Column("conversation_id", sa.String(length=36), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_message", sa.String(length=500), nullable=True),
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["conversation_id"], ["conversations.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_voice_sessions_conversation_id"), "voice_sessions", ["conversation_id"], unique=False)
    op.create_index(op.f("ix_voice_sessions_user_id"), "voice_sessions", ["user_id"], unique=False)
    op.create_index(op.f("ix_voice_sessions_workspace_id"), "voice_sessions", ["workspace_id"], unique=False)

    op.create_table(
        "voice_settings",
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("voice_enabled", sa.Boolean(), nullable=False),
        sa.Column("auto_speak_responses", sa.Boolean(), nullable=False),
        sa.Column("preferred_voice", sa.String(length=255), nullable=True),
        sa.Column("speech_speed", sa.Float(), nullable=False),
        sa.Column("speech_volume", sa.Float(), nullable=False),
        sa.Column("language", sa.String(length=20), nullable=False),
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id"),
    )
    op.create_index(op.f("ix_voice_settings_user_id"), "voice_settings", ["user_id"], unique=True)


def downgrade() -> None:
    op.drop_index(op.f("ix_voice_settings_user_id"), table_name="voice_settings")
    op.drop_table("voice_settings")
    op.drop_index(op.f("ix_voice_sessions_workspace_id"), table_name="voice_sessions")
    op.drop_index(op.f("ix_voice_sessions_user_id"), table_name="voice_sessions")
    op.drop_index(op.f("ix_voice_sessions_conversation_id"), table_name="voice_sessions")
    op.drop_table("voice_sessions")
