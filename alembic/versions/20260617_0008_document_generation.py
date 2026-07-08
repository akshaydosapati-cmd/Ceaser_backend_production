"""document generation and agent activity

Revision ID: 20260617_0008
Revises: 20260617_0007
Create Date: 2026-06-17
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20260617_0008"
down_revision: Union[str, None] = "20260617_0007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "generated_documents",
        sa.Column("file_id", sa.String(length=36), nullable=False),
        sa.Column("workspace_id", sa.String(length=36), nullable=False),
        sa.Column("agent_id", sa.String(length=80), nullable=False),
        sa.Column("template_id", sa.String(length=120), nullable=False),
        sa.Column("generated_by", sa.String(length=120), nullable=False),
        sa.Column("export_format", sa.String(length=20), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("source_prompt_encrypted", sa.Text(), nullable=True),
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["file_id"], ["files.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_generated_documents_agent_id"), "generated_documents", ["agent_id"], unique=False)
    op.create_index(op.f("ix_generated_documents_file_id"), "generated_documents", ["file_id"], unique=False)
    op.create_index(op.f("ix_generated_documents_workspace_id"), "generated_documents", ["workspace_id"], unique=False)
    op.create_table(
        "agent_activity",
        sa.Column("workspace_id", sa.String(length=36), nullable=False),
        sa.Column("file_id", sa.String(length=36), nullable=True),
        sa.Column("agent_id", sa.String(length=80), nullable=False),
        sa.Column("action", sa.String(length=80), nullable=False),
        sa.Column("detail_encrypted", sa.Text(), nullable=True),
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["file_id"], ["files.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_agent_activity_agent_id"), "agent_activity", ["agent_id"], unique=False)
    op.create_index(op.f("ix_agent_activity_file_id"), "agent_activity", ["file_id"], unique=False)
    op.create_index(op.f("ix_agent_activity_workspace_id"), "agent_activity", ["workspace_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_agent_activity_workspace_id"), table_name="agent_activity")
    op.drop_index(op.f("ix_agent_activity_file_id"), table_name="agent_activity")
    op.drop_index(op.f("ix_agent_activity_agent_id"), table_name="agent_activity")
    op.drop_table("agent_activity")
    op.drop_index(op.f("ix_generated_documents_workspace_id"), table_name="generated_documents")
    op.drop_index(op.f("ix_generated_documents_file_id"), table_name="generated_documents")
    op.drop_index(op.f("ix_generated_documents_agent_id"), table_name="generated_documents")
    op.drop_table("generated_documents")
