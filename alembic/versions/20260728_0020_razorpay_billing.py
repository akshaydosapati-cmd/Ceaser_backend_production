"""Add Razorpay billing fields, payments, and invoices.

Revision ID: 20260728_0020
Revises: 20260723_0019
Create Date: 2026-07-28
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision: str = "20260728_0020"
down_revision: str | None = "20260723_0019"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("subscriptions", sa.Column("provider_plan_id", sa.String(length=255), nullable=True))
    op.add_column("subscriptions", sa.Column("provider_payment_id", sa.String(length=255), nullable=True))
    op.add_column("subscriptions", sa.Column("provider_invoice_id", sa.String(length=255), nullable=True))
    op.add_column("subscriptions", sa.Column("currency", sa.String(length=10), nullable=False, server_default="INR"))
    op.add_column("subscriptions", sa.Column("next_renewal_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("subscriptions", sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("subscriptions", sa.Column("paused_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("subscriptions", sa.Column("extra_metadata", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")))

    op.create_table(
        "billing_payments",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("subscription_id", sa.String(length=36), nullable=True),
        sa.Column("plan_id", sa.String(length=36), nullable=True),
        sa.Column("provider", sa.String(length=40), nullable=False),
        sa.Column("provider_payment_id", sa.String(length=255), nullable=False),
        sa.Column("provider_invoice_id", sa.String(length=255), nullable=True),
        sa.Column("amount", sa.Integer(), nullable=False),
        sa.Column("currency", sa.String(length=10), nullable=False),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("method", sa.String(length=80), nullable=True),
        sa.Column("captured_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("extra_metadata", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["plan_id"], ["plans.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["subscription_id"], ["subscriptions.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("provider", "provider_payment_id", name="uq_billing_payment_provider_payment"),
    )
    op.create_index("ix_billing_payments_user_id", "billing_payments", ["user_id"])
    op.create_index("ix_billing_payments_subscription_id", "billing_payments", ["subscription_id"])

    op.create_table(
        "billing_invoices",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("subscription_id", sa.String(length=36), nullable=True),
        sa.Column("plan_id", sa.String(length=36), nullable=True),
        sa.Column("provider", sa.String(length=40), nullable=False),
        sa.Column("provider_invoice_id", sa.String(length=255), nullable=False),
        sa.Column("invoice_number", sa.String(length=120), nullable=True),
        sa.Column("amount", sa.Integer(), nullable=False),
        sa.Column("currency", sa.String(length=10), nullable=False),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("hosted_url", sa.Text(), nullable=True),
        sa.Column("issued_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("paid_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("extra_metadata", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["plan_id"], ["plans.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["subscription_id"], ["subscriptions.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("provider", "provider_invoice_id", name="uq_billing_invoice_provider_invoice"),
    )
    op.create_index("ix_billing_invoices_user_id", "billing_invoices", ["user_id"])
    op.create_index("ix_billing_invoices_subscription_id", "billing_invoices", ["subscription_id"])

    _enable_owner_rls("billing_payments", "user_id")
    _enable_owner_rls("billing_invoices", "user_id")


def downgrade() -> None:
    op.drop_table("billing_invoices")
    op.drop_table("billing_payments")
    for column in [
        "extra_metadata",
        "paused_at",
        "cancelled_at",
        "next_renewal_at",
        "currency",
        "provider_invoice_id",
        "provider_payment_id",
        "provider_plan_id",
    ]:
        op.drop_column("subscriptions", column)


def _enable_owner_rls(table: str, owner_column: str) -> None:
    condition = f"{owner_column} = auth.uid()::text"
    op.execute(f"alter table public.{table} enable row level security")
    op.execute(f"drop policy if exists {table}_owner_access on public.{table}")
    op.execute(f"create policy {table}_owner_access on public.{table} for all to authenticated using ({condition}) with check ({condition})")
