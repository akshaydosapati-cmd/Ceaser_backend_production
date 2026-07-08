"""add message metadata

Revision ID: 20260614_0002
Revises: 20260606_0001
Create Date: 2026-06-14
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260614_0002"
down_revision: str | None = "20260606_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("messages", sa.Column("metadata", sa.JSON(), nullable=True))
    op.execute("UPDATE messages SET metadata = '{}' WHERE metadata IS NULL")
    op.alter_column("messages", "metadata", nullable=False)


def downgrade() -> None:
    op.drop_column("messages", "metadata")
