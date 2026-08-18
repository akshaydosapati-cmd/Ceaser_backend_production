"""C7 resource policy configuration and shadow decisions.

Revision ID: 20260818_0038
Revises: 20260818_0037
"""
from alembic import op
import sqlalchemy as sa

revision = "20260818_0038"
down_revision = "20260818_0037"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "resource_policies",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("policy_version", sa.String(40), nullable=False),
        sa.Column("plan_key", sa.String(40), nullable=False),
        sa.Column("warning_threshold", sa.Numeric(8, 4), nullable=False),
        sa.Column("degrade_threshold", sa.Numeric(8, 4), nullable=False),
        sa.Column("hard_compute_threshold", sa.Numeric(20, 9), nullable=True),
        sa.Column("lite_enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("observe_only", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("allow_negative_shadow", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("effective_from", sa.DateTime(timezone=True), nullable=False),
        sa.Column("extra_metadata", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("policy_version", "plan_key", "effective_from", name="uq_resource_policy_version_plan"),
    )
    for name, columns in (("ix_resource_policies_policy_version", ["policy_version"]), ("ix_resource_policies_plan_key", ["plan_key"]), ("ix_resource_policies_enabled", ["enabled"]), ("ix_resource_policies_effective_from", ["effective_from"])):
        op.create_index(name, "resource_policies", columns)
    op.create_table(
        "policy_decisions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("request_id", sa.String(120), nullable=False),
        sa.Column("capability_key", sa.String(120), nullable=False),
        sa.Column("estimate_id", sa.String(36), sa.ForeignKey("usage_estimates.id", ondelete="SET NULL"), nullable=True),
        sa.Column("decision", sa.String(30), nullable=False),
        sa.Column("reason", sa.String(80), nullable=False),
        sa.Column("wallet_available_cu", sa.Numeric(20, 9), nullable=True),
        sa.Column("estimated_compute_units", sa.Numeric(20, 9), nullable=True),
        sa.Column("policy_version", sa.String(40), nullable=False),
        sa.Column("execution_mode", sa.String(30), nullable=False),
        sa.Column("fallback_mode", sa.String(30), nullable=True),
        sa.Column("requires_confirmation", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("enforced", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("extra_metadata", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("user_id", "request_id", "capability_key", "policy_version", name="uq_policy_decision_request_version"),
    )
    for name, columns in (("ix_policy_decisions_user_id", ["user_id"]), ("ix_policy_decisions_request_id", ["request_id"]), ("ix_policy_decisions_capability_key", ["capability_key"]), ("ix_policy_decisions_estimate_id", ["estimate_id"]), ("ix_policy_decisions_decision", ["decision"]), ("ix_policy_decisions_policy_version", ["policy_version"]), ("ix_policy_decisions_enforced", ["enforced"])):
        op.create_index(name, "policy_decisions", columns)


def downgrade() -> None:
    op.drop_table("policy_decisions")
    op.drop_table("resource_policies")
