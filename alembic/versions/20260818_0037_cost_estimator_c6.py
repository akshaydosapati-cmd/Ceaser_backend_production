"""C6 pre-execution cost estimates.

Revision ID: 20260818_0037
Revises: 20260818_0036
"""
from alembic import op
import sqlalchemy as sa

revision = "20260818_0037"
down_revision = "20260818_0036"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "usage_estimates",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("request_id", sa.String(120), nullable=False),
        sa.Column("capability_key", sa.String(120), nullable=False),
        sa.Column("context_bucket", sa.String(80), nullable=False),
        sa.Column("estimated_cost", sa.Numeric(20, 12), nullable=True),
        sa.Column("cost_currency", sa.String(10), nullable=True),
        sa.Column("estimated_compute_units", sa.Numeric(20, 9), nullable=True),
        sa.Column("confidence", sa.String(20), nullable=False),
        sa.Column("cost_class", sa.String(20), nullable=False),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("estimator_version", sa.String(20), nullable=False),
        sa.Column("basis", sa.String(80), nullable=False),
        sa.Column("breakdown", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("usage_ledger_id", sa.String(36), sa.ForeignKey("usage_ledger.id", ondelete="SET NULL"), nullable=True),
        sa.Column("actual_compute_units", sa.Numeric(20, 9), nullable=True),
        sa.Column("variance_percent", sa.Numeric(12, 4), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("user_id", "request_id", "capability_key", "estimator_version", name="uq_usage_estimate_request_version"),
    )
    for name, columns in (
        ("ix_usage_estimates_user_id", ["user_id"]), ("ix_usage_estimates_request_id", ["request_id"]),
        ("ix_usage_estimates_capability_key", ["capability_key"]), ("ix_usage_estimates_context_bucket", ["context_bucket"]),
        ("ix_usage_estimates_confidence", ["confidence"]), ("ix_usage_estimates_status", ["status"]),
        ("ix_usage_estimates_estimator_version", ["estimator_version"]), ("ix_usage_estimates_usage_ledger_id", ["usage_ledger_id"]),
    ):
        op.create_index(name, "usage_estimates", columns)


def downgrade() -> None:
    op.drop_table("usage_estimates")
