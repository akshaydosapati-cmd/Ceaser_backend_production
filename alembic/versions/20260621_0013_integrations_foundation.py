"""Add read-only integrations foundation.

Revision ID: 20260621_0013
Revises: 20260621_0012
Create Date: 2026-06-21
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision: str = "20260621_0013"
down_revision: str | None = "20260621_0012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "integrations",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("workspace_id", sa.String(length=36), nullable=True),
        sa.Column("provider", sa.String(length=80), nullable=False),
        sa.Column("provider_account_id", sa.String(length=255), nullable=True),
        sa.Column("provider_email", sa.String(length=255), nullable=True),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("access_token_encrypted", sa.Text(), nullable=True),
        sa.Column("refresh_token_encrypted", sa.Text(), nullable=True),
        sa.Column("token_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("metadata_json", sa.JSON(), nullable=False),
        sa.Column("last_sync_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_integrations_user_id", "integrations", ["user_id"])
    op.create_index("ix_integrations_workspace_id", "integrations", ["workspace_id"])
    op.create_index("ix_integrations_provider", "integrations", ["provider"])
    op.create_index("ix_integrations_status", "integrations", ["status"])
    op.create_unique_constraint("uq_integrations_user_provider", "integrations", ["user_id", "provider"])


def downgrade() -> None:
    op.drop_constraint("uq_integrations_user_provider", "integrations", type_="unique")
    op.drop_index("ix_integrations_status", table_name="integrations")
    op.drop_index("ix_integrations_provider", table_name="integrations")
    op.drop_index("ix_integrations_workspace_id", table_name="integrations")
    op.drop_index("ix_integrations_user_id", table_name="integrations")
    op.drop_table("integrations")
