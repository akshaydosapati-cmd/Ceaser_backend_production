"""Persist compact conversation continuity state.

Revision ID: 20260821_0040
Revises: 20260818_0039
"""
from alembic import op
import sqlalchemy as sa

revision = "20260821_0040"
down_revision = "20260818_0039"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("conversations", sa.Column("conversation_summary", sa.String(), nullable=True))
    op.add_column("conversations", sa.Column("summary_encrypted", sa.String(), nullable=True))
    op.add_column("conversations", sa.Column("conversation_state", sa.JSON(), nullable=False, server_default=sa.text("'{}'")))
    op.add_column("conversations", sa.Column("state_encrypted", sa.String(), nullable=True))
    op.add_column("conversations", sa.Column("summary_version", sa.Integer(), nullable=False, server_default="1"))
    op.add_column("conversations", sa.Column("state_updated_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    for name in ("state_updated_at", "summary_version", "state_encrypted", "conversation_state", "summary_encrypted", "conversation_summary"):
        op.drop_column("conversations", name)
