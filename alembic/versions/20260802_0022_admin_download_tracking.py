"""Add admin download tracking.

Revision ID: 20260802_0022
Revises: 20260728_0021
Create Date: 2026-08-02
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision: str = "20260802_0022"
down_revision: str | None = "20260728_0021"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "download_events",
        sa.Column("user_id", sa.String(length=36), nullable=True),
        sa.Column("source", sa.String(length=80), nullable=False, server_default="website"),
        sa.Column("platform", sa.String(length=80), nullable=False, server_default="windows"),
        sa.Column("version", sa.String(length=80), nullable=True),
        sa.Column("user_agent", sa.String(length=500), nullable=True),
        sa.Column("ip_hash", sa.String(length=128), nullable=True),
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_download_events_user_id", "download_events", ["user_id"])
    op.create_index("ix_download_events_source", "download_events", ["source"])
    op.create_index("ix_download_events_platform", "download_events", ["platform"])
    op.create_index("ix_download_events_ip_hash", "download_events", ["ip_hash"])
    op.execute("alter table public.download_events enable row level security")
    op.execute("create policy download_events_service_role_access on public.download_events for all to service_role using (true) with check (true)")


def downgrade() -> None:
    op.execute("drop policy if exists download_events_service_role_access on public.download_events")
    op.drop_index("ix_download_events_ip_hash", table_name="download_events")
    op.drop_index("ix_download_events_platform", table_name="download_events")
    op.drop_index("ix_download_events_source", table_name="download_events")
    op.drop_index("ix_download_events_user_id", table_name="download_events")
    op.drop_table("download_events")
