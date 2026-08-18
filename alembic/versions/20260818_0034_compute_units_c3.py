"""C3 versioned compute-unit conversion policy.

Revision ID: 20260818_0034
Revises: 20260818_0033
"""
from alembic import op
import sqlalchemy as sa

revision = "20260818_0034"
down_revision = "20260818_0033"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "compute_unit_policies",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("name", sa.String(80), nullable=False),
        sa.Column("currency", sa.String(10), nullable=False),
        sa.Column("cost_per_compute_unit", sa.Numeric(20, 12), nullable=False),
        sa.Column("effective_from", sa.DateTime(timezone=True), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("extra_metadata", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("name", "currency", "effective_from", name="uq_compute_unit_policy_version"),
    )
    for name, columns in (("ix_compute_unit_policies_name", ["name"]), ("ix_compute_unit_policies_currency", ["currency"]), ("ix_compute_unit_policies_effective_from", ["effective_from"]), ("ix_compute_unit_policies_enabled", ["enabled"])):
        op.create_index(name, "compute_unit_policies", columns)
    op.execute("update usage_ledger set compute_units = null")
    op.alter_column("usage_ledger", "compute_units", existing_type=sa.Float(), type_=sa.Numeric(20, 9), nullable=True, server_default=None)
    op.add_column("usage_ledger", sa.Column("compute_unit_status", sa.String(30), nullable=False, server_default="unpriced"))
    op.add_column("usage_ledger", sa.Column("compute_unit_policy_id", sa.String(36), nullable=True))
    op.create_foreign_key("fk_usage_ledger_compute_unit_policy", "usage_ledger", "compute_unit_policies", ["compute_unit_policy_id"], ["id"], ondelete="SET NULL")
    op.create_index("ix_usage_ledger_compute_unit_status", "usage_ledger", ["compute_unit_status"])


def downgrade() -> None:
    op.drop_index("ix_usage_ledger_compute_unit_status", table_name="usage_ledger")
    op.drop_constraint("fk_usage_ledger_compute_unit_policy", "usage_ledger", type_="foreignkey")
    op.drop_column("usage_ledger", "compute_unit_policy_id")
    op.drop_column("usage_ledger", "compute_unit_status")
    op.execute("update usage_ledger set compute_units = 0 where compute_units is null")
    op.alter_column("usage_ledger", "compute_units", existing_type=sa.Numeric(20, 9), type_=sa.Float(), nullable=False, server_default="0")
    op.drop_table("compute_unit_policies")
