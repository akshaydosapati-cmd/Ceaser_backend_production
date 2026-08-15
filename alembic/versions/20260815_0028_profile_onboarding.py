"""Persist onboarding details in profiles.

Revision ID: 20260815_0028
Revises: 20260812_0027
"""

from alembic import op
import sqlalchemy as sa


revision = "20260815_0028"
down_revision = "20260812_0027"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("profiles", sa.Column("use_case", sa.String(length=50), nullable=True))
    op.add_column("profiles", sa.Column("onboarding_data", sa.JSON(), nullable=True))
    op.add_column(
        "profiles",
        sa.Column("onboarding_completed", sa.Boolean(), nullable=False, server_default=sa.false()),
    )


def downgrade() -> None:
    op.drop_column("profiles", "onboarding_completed")
    op.drop_column("profiles", "onboarding_data")
    op.drop_column("profiles", "use_case")
