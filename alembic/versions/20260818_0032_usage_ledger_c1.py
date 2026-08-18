"""C1 unified usage ledger telemetry.

Revision ID: 20260818_0032
Revises: 20260818_0031
"""
from alembic import op
import sqlalchemy as sa

revision = "20260818_0032"
down_revision = "20260818_0031"
branch_labels = None
depends_on = None


def upgrade() -> None:
    columns = (
        sa.Column("operation", sa.String(120), nullable=False, server_default="unknown"),
        sa.Column("provider", sa.String(80), nullable=True),
        sa.Column("model", sa.String(160), nullable=True),
        sa.Column("status", sa.String(30), nullable=False, server_default="completed"),
        sa.Column("voice_input_seconds", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("voice_output_seconds", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("web_searches", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("image_generations", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("tool_calls", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("actual_cost", sa.Float(), nullable=False, server_default="0"),
        sa.Column("compute_units", sa.Float(), nullable=False, server_default="0"),
        sa.Column("idempotency_key", sa.String(180), nullable=True),
    )
    for column in columns:
        op.add_column("usage_ledger", column)
    op.create_index("ix_usage_ledger_operation", "usage_ledger", ["operation"])
    op.create_index("ix_usage_ledger_provider", "usage_ledger", ["provider"])
    op.create_index("ix_usage_ledger_status", "usage_ledger", ["status"])
    op.create_unique_constraint("uq_usage_ledger_idempotency_key", "usage_ledger", ["idempotency_key"])


def downgrade() -> None:
    op.drop_constraint("uq_usage_ledger_idempotency_key", "usage_ledger", type_="unique")
    for index in ("ix_usage_ledger_status", "ix_usage_ledger_provider", "ix_usage_ledger_operation"):
        op.drop_index(index, table_name="usage_ledger")
    for column in ("idempotency_key", "compute_units", "actual_cost", "tool_calls", "image_generations", "web_searches", "voice_output_seconds", "voice_input_seconds", "status", "model", "provider", "operation"):
        op.drop_column("usage_ledger", column)
