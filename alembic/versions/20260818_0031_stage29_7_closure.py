"""Stage 29.7 closure indexes for concurrent metering and workflow lookup.

Revision ID: 20260818_0031
Revises: 20260818_0030
"""
from alembic import op

revision = "20260818_0031"
down_revision = "20260818_0030"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index("ix_credit_reservations_user_id", "credit_reservations", ["user_id"])
    op.create_index("ix_referrals_referrer_user_id", "referrals", ["referrer_user_id"])
    op.create_index("ix_referrals_referred_user_id", "referrals", ["referred_user_id"])
    op.create_index("ix_credit_purchases_user_id", "credit_purchases", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_credit_purchases_user_id", table_name="credit_purchases")
    op.drop_index("ix_referrals_referred_user_id", table_name="referrals")
    op.drop_index("ix_referrals_referrer_user_id", table_name="referrals")
    op.drop_index("ix_credit_reservations_user_id", table_name="credit_reservations")
