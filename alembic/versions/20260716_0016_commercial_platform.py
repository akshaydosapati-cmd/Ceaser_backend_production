"""Add commercial plans, usage, billing, and student verification.

Revision ID: 20260716_0016
Revises: 20260706_0015
Create Date: 2026-07-16
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision: str = "20260716_0016"
down_revision: str | None = "20260706_0015"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "plans",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("code", sa.String(length=40), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("currency", sa.String(length=10), nullable=False),
        sa.Column("monthly_price", sa.Integer(), nullable=False),
        sa.Column("annual_price", sa.Integer(), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("public", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("code"),
    )
    op.create_index("ix_plans_code", "plans", ["code"])

    op.create_table(
        "institutions",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("code", sa.String(length=80), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
        sa.UniqueConstraint("code"),
    )
    op.create_index("ix_institutions_code", "institutions", ["code"])

    op.create_table(
        "plan_entitlements",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("plan_id", sa.String(length=36), nullable=False),
        sa.Column("entitlement_key", sa.String(length=80), nullable=False),
        sa.Column("limit_value", sa.Integer(), nullable=False),
        sa.Column("value_type", sa.String(length=30), nullable=False),
        sa.Column("reset_period", sa.String(length=30), nullable=False),
        sa.Column("extra_metadata", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["plan_id"], ["plans.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("plan_id", "entitlement_key", name="uq_plan_entitlement_key"),
    )
    op.create_index("ix_plan_entitlements_plan_id", "plan_entitlements", ["plan_id"])
    op.create_index("ix_plan_entitlements_entitlement_key", "plan_entitlements", ["entitlement_key"])

    op.create_table(
        "institution_domains",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("institution_id", sa.String(length=36), nullable=False),
        sa.Column("domain", sa.String(length=255), nullable=False),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("instant_approval_enabled", sa.Boolean(), nullable=False),
        sa.Column("approved_by", sa.String(length=36), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["approved_by"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["institution_id"], ["institutions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("domain", name="uq_institution_domain"),
    )
    op.create_index("ix_institution_domains_institution_id", "institution_domains", ["institution_id"])
    op.create_index("ix_institution_domains_domain", "institution_domains", ["domain"])

    op.create_table(
        "subscriptions",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("plan_id", sa.String(length=36), nullable=False),
        sa.Column("provider", sa.String(length=40), nullable=False),
        sa.Column("provider_customer_id", sa.String(length=255), nullable=True),
        sa.Column("provider_subscription_id", sa.String(length=255), nullable=True),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("billing_interval", sa.String(length=20), nullable=False),
        sa.Column("current_period_start", sa.DateTime(timezone=True), nullable=True),
        sa.Column("current_period_end", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancel_at_period_end", sa.Boolean(), nullable=False),
        sa.Column("grace_period_end", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["plan_id"], ["plans.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_subscriptions_user_id", "subscriptions", ["user_id"])
    op.create_index("ix_subscriptions_plan_id", "subscriptions", ["plan_id"])
    op.create_index("ix_subscriptions_status", "subscriptions", ["status"])

    op.create_table(
        "student_verifications",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("institution_id", sa.String(length=36), nullable=True),
        sa.Column("institutional_email", sa.String(length=255), nullable=True),
        sa.Column("verification_method", sa.String(length=40), nullable=True),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("document_file_id", sa.String(length=36), nullable=True),
        sa.Column("otp_requested_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("rejection_reason", sa.Text(), nullable=True),
        sa.Column("reviewed_by", sa.String(length=36), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["document_file_id"], ["files.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["institution_id"], ["institutions.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["reviewed_by"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_student_verifications_user_id", "student_verifications", ["user_id"])
    op.create_index("ix_student_verifications_institutional_email", "student_verifications", ["institutional_email"])
    op.create_index("ix_student_verifications_status", "student_verifications", ["status"])

    op.create_table(
        "usage_counters",
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("entitlement_key", sa.String(length=80), nullable=False),
        sa.Column("period_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("period_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_quantity", sa.Integer(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("user_id", "entitlement_key", "period_start", "period_end"),
        sa.UniqueConstraint("user_id", "entitlement_key", "period_start", "period_end", name="uq_usage_counter_period"),
    )

    op.create_table(
        "usage_ledger",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("subscription_id", sa.String(length=36), nullable=True),
        sa.Column("plan_id", sa.String(length=36), nullable=True),
        sa.Column("action_type", sa.String(length=80), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("input_tokens", sa.Integer(), nullable=False),
        sa.Column("output_tokens", sa.Integer(), nullable=False),
        sa.Column("embedding_tokens", sa.Integer(), nullable=False),
        sa.Column("voice_seconds", sa.Integer(), nullable=False),
        sa.Column("estimated_cost", sa.Float(), nullable=False),
        sa.Column("request_id", sa.String(length=120), nullable=True),
        sa.Column("extra_metadata", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["plan_id"], ["plans.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["subscription_id"], ["subscriptions.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_usage_ledger_user_id", "usage_ledger", ["user_id"])
    op.create_index("ix_usage_ledger_action_type", "usage_ledger", ["action_type"])

    op.create_table(
        "verification_attempts",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("verification_id", sa.String(length=36), nullable=False),
        sa.Column("method", sa.String(length=40), nullable=False),
        sa.Column("email_hash", sa.String(length=128), nullable=True),
        sa.Column("ip_hash", sa.String(length=128), nullable=True),
        sa.Column("result", sa.String(length=40), nullable=False),
        sa.Column("failure_reason", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["verification_id"], ["student_verifications.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_verification_attempts_verification_id", "verification_attempts", ["verification_id"])
    op.create_index("ix_verification_attempts_email_hash", "verification_attempts", ["email_hash"])
    op.create_index("ix_verification_attempts_ip_hash", "verification_attempts", ["ip_hash"])

    op.create_table(
        "billing_events",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("provider", sa.String(length=40), nullable=False),
        sa.Column("provider_event_id", sa.String(length=255), nullable=False),
        sa.Column("event_type", sa.String(length=80), nullable=False),
        sa.Column("signature_verified", sa.Boolean(), nullable=False),
        sa.Column("payload_hash", sa.String(length=128), nullable=True),
        sa.Column("processing_status", sa.String(length=40), nullable=False),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("failure_reason", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("provider", "provider_event_id", name="uq_billing_provider_event"),
    )

    _enable_owner_rls("subscriptions", "user_id")
    _enable_owner_rls("usage_ledger", "user_id")
    _enable_owner_rls("usage_counters", "user_id")
    _enable_owner_rls("student_verifications", "user_id")
    _enable_indirect_rls(
        "verification_attempts",
        "exists (select 1 from public.student_verifications sv where sv.id = verification_id and sv.user_id = auth.uid()::text)",
    )
    _enable_public_read("plans")
    _enable_public_read("plan_entitlements")
    _enable_public_read("institutions")
    _enable_public_read("institution_domains")


def downgrade() -> None:
    for table in [
        "billing_events",
        "verification_attempts",
        "usage_ledger",
        "usage_counters",
        "student_verifications",
        "subscriptions",
        "institution_domains",
        "plan_entitlements",
        "institutions",
        "plans",
    ]:
        op.drop_table(table)


def _enable_owner_rls(table: str, owner_column: str) -> None:
    condition = f"{owner_column} = auth.uid()::text"
    op.execute(f"alter table public.{table} enable row level security")
    op.execute(f"drop policy if exists {table}_owner_access on public.{table}")
    op.execute(f"create policy {table}_owner_access on public.{table} for all to authenticated using ({condition}) with check ({condition})")


def _enable_indirect_rls(table: str, condition: str) -> None:
    op.execute(f"alter table public.{table} enable row level security")
    op.execute(f"drop policy if exists {table}_owner_access on public.{table}")
    op.execute(f"create policy {table}_owner_access on public.{table} for all to authenticated using ({condition}) with check ({condition})")


def _enable_public_read(table: str) -> None:
    op.execute(f"alter table public.{table} enable row level security")
    op.execute(f"drop policy if exists {table}_authenticated_read on public.{table}")
    op.execute(f"create policy {table}_authenticated_read on public.{table} for select to authenticated using (true)")
