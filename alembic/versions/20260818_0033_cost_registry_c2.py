"""C2 versioned provider cost registry.

Revision ID: 20260818_0033
Revises: 20260818_0032
"""
from alembic import op
import sqlalchemy as sa

revision = "20260818_0033"
down_revision = "20260818_0032"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "provider_cost_rates",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("provider", sa.String(80), nullable=False),
        sa.Column("service", sa.String(80), nullable=False),
        sa.Column("operation", sa.String(120), nullable=False),
        sa.Column("pricing_unit", sa.String(40), nullable=False),
        sa.Column("input_unit_cost", sa.Numeric(20, 12), nullable=False, server_default="0"),
        sa.Column("output_unit_cost", sa.Numeric(20, 12), nullable=False, server_default="0"),
        sa.Column("currency", sa.String(10), nullable=False, server_default="USD"),
        sa.Column("effective_from", sa.DateTime(timezone=True), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("extra_metadata", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("provider", "service", "operation", "effective_from", name="uq_provider_cost_rate_version"),
    )
    for name, columns in (("ix_provider_cost_rates_provider", ["provider"]), ("ix_provider_cost_rates_service", ["service"]), ("ix_provider_cost_rates_operation", ["operation"]), ("ix_provider_cost_rates_effective_from", ["effective_from"]), ("ix_provider_cost_rates_enabled", ["enabled"])):
        op.create_index(name, "provider_cost_rates", columns)
    op.add_column("usage_ledger", sa.Column("cost_currency", sa.String(10), nullable=True))
    op.add_column("usage_ledger", sa.Column("pricing_status", sa.String(30), nullable=False, server_default="unpriced"))
    op.add_column("usage_ledger", sa.Column("pricing_rate_id", sa.String(36), nullable=True))
    op.create_foreign_key("fk_usage_ledger_pricing_rate", "usage_ledger", "provider_cost_rates", ["pricing_rate_id"], ["id"], ondelete="SET NULL")
    op.create_index("ix_usage_ledger_pricing_status", "usage_ledger", ["pricing_status"])


def downgrade() -> None:
    op.drop_index("ix_usage_ledger_pricing_status", table_name="usage_ledger")
    op.drop_constraint("fk_usage_ledger_pricing_rate", "usage_ledger", type_="foreignkey")
    for column in ("pricing_rate_id", "pricing_status", "cost_currency"):
        op.drop_column("usage_ledger", column)
    op.drop_table("provider_cost_rates")
