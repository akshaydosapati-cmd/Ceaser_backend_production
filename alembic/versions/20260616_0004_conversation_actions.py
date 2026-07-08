"""conversation actions

Revision ID: 20260616_0004
Revises: 20260616_0003
Create Date: 2026-06-16
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260616_0004"
down_revision: str | None = "20260616_0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("conversations", sa.Column("pinned", sa.Boolean(), nullable=True))
    op.add_column("conversations", sa.Column("archived", sa.Boolean(), nullable=True))
    op.execute("UPDATE conversations SET pinned = false WHERE pinned IS NULL")
    op.execute("UPDATE conversations SET archived = false WHERE archived IS NULL")
    op.alter_column("conversations", "pinned", nullable=False)
    op.alter_column("conversations", "archived", nullable=False)


def downgrade() -> None:
    op.drop_column("conversations", "archived")
    op.drop_column("conversations", "pinned")
