"""C5 capability identity on usage ledger.

Revision ID: 20260818_0036
Revises: 20260818_0035
"""
from alembic import op
import sqlalchemy as sa

revision = "20260818_0036"
down_revision = "20260818_0035"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("usage_ledger", sa.Column("capability_key", sa.String(120), nullable=True))
    op.add_column("usage_ledger", sa.Column("capability_category", sa.String(80), nullable=True))
    op.add_column("usage_ledger", sa.Column("execution_type", sa.String(30), nullable=True))
    op.create_index("ix_usage_ledger_capability_key", "usage_ledger", ["capability_key"])
    op.create_index("ix_usage_ledger_capability_category", "usage_ledger", ["capability_category"])
    op.create_index("ix_usage_ledger_execution_type", "usage_ledger", ["execution_type"])


def downgrade() -> None:
    op.drop_index("ix_usage_ledger_execution_type", table_name="usage_ledger")
    op.drop_index("ix_usage_ledger_capability_category", table_name="usage_ledger")
    op.drop_index("ix_usage_ledger_capability_key", table_name="usage_ledger")
    op.drop_column("usage_ledger", "execution_type")
    op.drop_column("usage_ledger", "capability_category")
    op.drop_column("usage_ledger", "capability_key")
