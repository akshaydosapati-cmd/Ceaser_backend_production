"""draft engine

Revision ID: 20260617_0009
Revises: 20260617_0008
Create Date: 2026-06-17
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20260617_0009"
down_revision: Union[str, None] = "20260617_0008"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "drafts",
        sa.Column("workspace_id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("agent_id", sa.String(length=80), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("draft_type", sa.String(length=80), nullable=False),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("progress", sa.Integer(), nullable=False),
        sa.Column("source_prompt_encrypted", sa.Text(), nullable=True),
        sa.Column("content_encrypted", sa.Text(), nullable=True),
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_drafts_agent_id"), "drafts", ["agent_id"], unique=False)
    op.create_index(op.f("ix_drafts_draft_type"), "drafts", ["draft_type"], unique=False)
    op.create_index(op.f("ix_drafts_status"), "drafts", ["status"], unique=False)
    op.create_index(op.f("ix_drafts_user_id"), "drafts", ["user_id"], unique=False)
    op.create_index(op.f("ix_drafts_workspace_id"), "drafts", ["workspace_id"], unique=False)

    op.create_table(
        "draft_history",
        sa.Column("draft_id", sa.String(length=36), nullable=False),
        sa.Column("workspace_id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("agent_id", sa.String(length=80), nullable=False),
        sa.Column("action", sa.String(length=80), nullable=False),
        sa.Column("detail_encrypted", sa.Text(), nullable=True),
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["draft_id"], ["drafts.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_draft_history_agent_id"), "draft_history", ["agent_id"], unique=False)
    op.create_index(op.f("ix_draft_history_draft_id"), "draft_history", ["draft_id"], unique=False)
    op.create_index(op.f("ix_draft_history_user_id"), "draft_history", ["user_id"], unique=False)
    op.create_index(op.f("ix_draft_history_workspace_id"), "draft_history", ["workspace_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_draft_history_workspace_id"), table_name="draft_history")
    op.drop_index(op.f("ix_draft_history_user_id"), table_name="draft_history")
    op.drop_index(op.f("ix_draft_history_draft_id"), table_name="draft_history")
    op.drop_index(op.f("ix_draft_history_agent_id"), table_name="draft_history")
    op.drop_table("draft_history")
    op.drop_index(op.f("ix_drafts_workspace_id"), table_name="drafts")
    op.drop_index(op.f("ix_drafts_user_id"), table_name="drafts")
    op.drop_index(op.f("ix_drafts_status"), table_name="drafts")
    op.drop_index(op.f("ix_drafts_draft_type"), table_name="drafts")
    op.drop_index(op.f("ix_drafts_agent_id"), table_name="drafts")
    op.drop_table("drafts")
