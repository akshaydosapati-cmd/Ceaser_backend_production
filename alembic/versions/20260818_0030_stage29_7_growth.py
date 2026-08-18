"""Stage 29.7 credit wallet, referrals, and credit purchases.

Revision ID: 20260818_0030
Revises: 20260815_0029
"""
from alembic import op
import sqlalchemy as sa

revision = "20260818_0030"
down_revision = "20260815_0029"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table("credit_wallets", sa.Column("id", sa.String(36), primary_key=True), sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False), sa.Column("plan", sa.String(40), nullable=False, server_default="FREE"), sa.Column("monthly_balance", sa.Integer, nullable=False, server_default="0"), sa.Column("bonus_balance", sa.Integer, nullable=False, server_default="0"), sa.Column("purchased_balance", sa.Integer, nullable=False, server_default="0"), sa.Column("reserved_balance", sa.Integer, nullable=False, server_default="0"), sa.Column("cycle_start", sa.DateTime(timezone=True), nullable=False), sa.Column("cycle_end", sa.DateTime(timezone=True), nullable=False), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False), sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False), sa.UniqueConstraint("user_id", name="uq_credit_wallet_user"))
    op.create_index("ix_credit_wallets_user_id", "credit_wallets", ["user_id"])
    op.create_table("credit_ledger", sa.Column("id", sa.String(36), primary_key=True), sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False), sa.Column("amount", sa.Integer, nullable=False), sa.Column("balance_type", sa.String(30), nullable=False), sa.Column("transaction_type", sa.String(40), nullable=False), sa.Column("source", sa.String(80), nullable=False), sa.Column("request_id", sa.String(120)), sa.Column("external_reference", sa.String(255)), sa.Column("extra_metadata", sa.JSON, nullable=False), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False), sa.UniqueConstraint("user_id", "request_id", "transaction_type", name="uq_credit_ledger_request_type"))
    op.create_index("ix_credit_ledger_user_id", "credit_ledger", ["user_id"])
    op.create_table("credit_reservations", sa.Column("id", sa.String(36), primary_key=True), sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False), sa.Column("request_id", sa.String(120), nullable=False), sa.Column("workload", sa.String(80), nullable=False), sa.Column("estimated_credits", sa.Integer, nullable=False), sa.Column("settled_credits", sa.Integer, nullable=False, server_default="0"), sa.Column("status", sa.String(30), nullable=False), sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False), sa.UniqueConstraint("user_id", "request_id", name="uq_credit_reservation_request"))
    op.create_table("referral_codes", sa.Column("id", sa.String(36), primary_key=True), sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False), sa.Column("code", sa.String(40), nullable=False), sa.Column("active", sa.Boolean, nullable=False), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False), sa.UniqueConstraint("user_id", name="uq_referral_code_user"), sa.UniqueConstraint("code", name="uq_referral_code"))
    op.create_table("referrals", sa.Column("id", sa.String(36), primary_key=True), sa.Column("referrer_user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False), sa.Column("referred_user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False), sa.Column("referral_code", sa.String(40), nullable=False), sa.Column("status", sa.String(30), nullable=False), sa.Column("rewarded_at", sa.DateTime(timezone=True)), sa.Column("suspicious", sa.Boolean, nullable=False), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False), sa.UniqueConstraint("referred_user_id", name="uq_referral_referred_user"))
    op.create_table("credit_products", sa.Column("id", sa.String(36), primary_key=True), sa.Column("code", sa.String(50), nullable=False, unique=True), sa.Column("name", sa.String(100), nullable=False), sa.Column("credits", sa.Integer, nullable=False), sa.Column("amount_inr", sa.Integer, nullable=False), sa.Column("active", sa.Boolean, nullable=False), sa.Column("plan_eligibility", sa.JSON, nullable=False), sa.Column("display_order", sa.Integer, nullable=False), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False))
    op.create_table("credit_purchases", sa.Column("id", sa.String(36), primary_key=True), sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False), sa.Column("credit_product_id", sa.String(36), sa.ForeignKey("credit_products.id"), nullable=False), sa.Column("razorpay_order_id", sa.String(255), nullable=False), sa.Column("razorpay_payment_id", sa.String(255)), sa.Column("amount", sa.Integer, nullable=False), sa.Column("credits", sa.Integer, nullable=False), sa.Column("status", sa.String(30), nullable=False), sa.Column("completed_at", sa.DateTime(timezone=True)), sa.Column("extra_metadata", sa.JSON, nullable=False), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False), sa.UniqueConstraint("razorpay_order_id", name="uq_credit_purchase_order"), sa.UniqueConstraint("razorpay_payment_id", name="uq_credit_purchase_payment"))
    for table, column in (("credit_wallets", "user_id"), ("credit_ledger", "user_id"), ("credit_reservations", "user_id"), ("referral_codes", "user_id"), ("credit_purchases", "user_id")):
        op.execute(f"alter table public.{table} enable row level security")
        op.execute(f"create policy {table}_owner_access on public.{table} for all to authenticated using ({column} = auth.uid()::text) with check ({column} = auth.uid()::text)")
    op.execute("alter table public.referrals enable row level security")
    op.execute("create policy referrals_owner_access on public.referrals for select to authenticated using (referrer_user_id = auth.uid()::text or referred_user_id = auth.uid()::text)")


def downgrade() -> None:
    for table in ("credit_purchases", "credit_products", "referrals", "referral_codes", "credit_reservations", "credit_ledger", "credit_wallets"):
        op.drop_table(table)
