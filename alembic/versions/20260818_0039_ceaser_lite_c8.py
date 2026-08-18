"""C8 effective Lite execution telemetry.

Revision ID: 20260818_0039
Revises: 20260818_0038
"""
from alembic import op
import sqlalchemy as sa

revision = "20260818_0039"
down_revision = "20260818_0038"
branch_labels = None
depends_on = None


def upgrade() -> None:
    columns = (
        sa.Column("requested_execution_mode", sa.String(30), nullable=True),
        sa.Column("effective_execution_mode", sa.String(30), nullable=True),
        sa.Column("fallback_used", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("fallback_capability", sa.String(120), nullable=True),
        sa.Column("upgrade_prompted", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("response_key", sa.String(80), nullable=True),
        sa.Column("lite_behavior_version", sa.String(30), nullable=True),
        sa.Column("rollout_mode", sa.String(30), nullable=True),
    )
    for column in columns:
        op.add_column("policy_decisions", column)
    op.create_index("ix_policy_decisions_effective_execution_mode", "policy_decisions", ["effective_execution_mode"])


def downgrade() -> None:
    op.drop_index("ix_policy_decisions_effective_execution_mode", table_name="policy_decisions")
    for name in ("rollout_mode", "lite_behavior_version", "response_key", "upgrade_prompted", "fallback_capability", "fallback_used", "effective_execution_mode", "requested_execution_mode"):
        op.drop_column("policy_decisions", name)
