"""C4 shadow compute wallet accounting.

Revision ID: 20260818_0035
Revises: 20260818_0034
"""
from alembic import op
import sqlalchemy as sa

revision = "20260818_0035"
down_revision = "20260818_0034"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "compute_wallets",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("plan_key", sa.String(40), nullable=True),
        sa.Column("period_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("period_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column("included_cu", sa.Numeric(20, 9), nullable=True),
        sa.Column("bonus_cu", sa.Numeric(20, 9), nullable=False, server_default="0"),
        sa.Column("used_cu", sa.Numeric(20, 9), nullable=False, server_default="0"),
        sa.Column("reserved_cu", sa.Numeric(20, 9), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("user_id", "period_start", "period_end", name="uq_compute_wallet_user_period"),
    )
    for name, columns in (
        ("ix_compute_wallets_user_id", ["user_id"]), ("ix_compute_wallets_plan_key", ["plan_key"]),
        ("ix_compute_wallets_period_start", ["period_start"]), ("ix_compute_wallets_period_end", ["period_end"]),
    ):
        op.create_index(name, "compute_wallets", columns)
    op.create_table(
        "compute_wallet_transactions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("wallet_id", sa.String(36), sa.ForeignKey("compute_wallets.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("request_id", sa.String(120), nullable=True),
        sa.Column("transaction_type", sa.String(30), nullable=False),
        sa.Column("amount_cu", sa.Numeric(20, 9), nullable=False),
        sa.Column("source", sa.String(80), nullable=False),
        sa.Column("reference_id", sa.String(120), nullable=True),
        sa.Column("idempotency_key", sa.String(220), nullable=False),
        sa.Column("extra_metadata", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("idempotency_key", name="uq_compute_wallet_transaction_idempotency"),
    )
    for name, columns in (
        ("ix_compute_wallet_transactions_wallet_id", ["wallet_id"]), ("ix_compute_wallet_transactions_user_id", ["user_id"]),
        ("ix_compute_wallet_transactions_request_id", ["request_id"]), ("ix_compute_wallet_transactions_transaction_type", ["transaction_type"]),
        ("ix_compute_wallet_transactions_source", ["source"]), ("ix_compute_wallet_transactions_reference_id", ["reference_id"]),
    ):
        op.create_index(name, "compute_wallet_transactions", columns)


def downgrade() -> None:
    op.drop_table("compute_wallet_transactions")
    op.drop_table("compute_wallets")
