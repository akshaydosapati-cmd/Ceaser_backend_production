"""Create launch_waitlist table.

Revision ID: 20260723_0019
Revises: 20260716_0018
Create Date: 2026-07-23
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "20260723_0019"
down_revision: str | None = "20260716_0018"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "launch_waitlist",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=True),
        sa.Column("source", sa.String(length=100), nullable=False, server_default="website"),
        sa.Column("status", sa.String(length=50), nullable=False, server_default="active"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_launch_waitlist_email", "launch_waitlist", ["email"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_launch_waitlist_email", table_name="launch_waitlist")
    op.drop_table("launch_waitlist")
