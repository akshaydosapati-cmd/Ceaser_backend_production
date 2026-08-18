from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, JSON, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database.base import Base
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin, utc_now


class Plan(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "plans"

    code: Mapped[str] = mapped_column(String(40), unique=True, index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="", nullable=False)
    currency: Mapped[str] = mapped_column(String(10), default="INR", nullable=False)
    monthly_price: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    annual_price: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    public: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False)


class PlanEntitlement(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "plan_entitlements"
    __table_args__ = (UniqueConstraint("plan_id", "entitlement_key", name="uq_plan_entitlement_key"),)

    plan_id: Mapped[str] = mapped_column(ForeignKey("plans.id", ondelete="CASCADE"), index=True, nullable=False)
    entitlement_key: Mapped[str] = mapped_column(String(80), index=True, nullable=False)
    limit_value: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    value_type: Mapped[str] = mapped_column(String(30), default="count", nullable=False)
    reset_period: Mapped[str] = mapped_column(String(30), default="monthly", nullable=False)
    extra_metadata: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)


class Subscription(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "subscriptions"

    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    plan_id: Mapped[str] = mapped_column(ForeignKey("plans.id"), index=True, nullable=False)
    provider: Mapped[str] = mapped_column(String(40), default="test", nullable=False)
    provider_plan_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    provider_customer_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    provider_subscription_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    provider_payment_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    provider_invoice_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    currency: Mapped[str] = mapped_column(String(10), default="INR", nullable=False)
    status: Mapped[str] = mapped_column(String(40), default="active", index=True, nullable=False)
    billing_interval: Mapped[str] = mapped_column(String(20), default="monthly", nullable=False)
    current_period_start: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    current_period_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    next_renewal_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cancel_at_period_end: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    paused_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    grace_period_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    extra_metadata: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False)


class BillingPayment(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "billing_payments"
    __table_args__ = (UniqueConstraint("provider", "provider_payment_id", name="uq_billing_payment_provider_payment"),)

    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    subscription_id: Mapped[str | None] = mapped_column(ForeignKey("subscriptions.id", ondelete="SET NULL"), index=True, nullable=True)
    plan_id: Mapped[str | None] = mapped_column(ForeignKey("plans.id", ondelete="SET NULL"), nullable=True)
    provider: Mapped[str] = mapped_column(String(40), nullable=False)
    provider_payment_id: Mapped[str] = mapped_column(String(255), nullable=False)
    provider_invoice_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    amount: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    currency: Mapped[str] = mapped_column(String(10), default="INR", nullable=False)
    status: Mapped[str] = mapped_column(String(40), default="created", nullable=False)
    method: Mapped[str | None] = mapped_column(String(80), nullable=True)
    captured_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    extra_metadata: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)


class BillingInvoice(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "billing_invoices"
    __table_args__ = (UniqueConstraint("provider", "provider_invoice_id", name="uq_billing_invoice_provider_invoice"),)

    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    subscription_id: Mapped[str | None] = mapped_column(ForeignKey("subscriptions.id", ondelete="SET NULL"), index=True, nullable=True)
    plan_id: Mapped[str | None] = mapped_column(ForeignKey("plans.id", ondelete="SET NULL"), nullable=True)
    provider: Mapped[str] = mapped_column(String(40), nullable=False)
    provider_invoice_id: Mapped[str] = mapped_column(String(255), nullable=False)
    invoice_number: Mapped[str | None] = mapped_column(String(120), nullable=True)
    amount: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    currency: Mapped[str] = mapped_column(String(10), default="INR", nullable=False)
    status: Mapped[str] = mapped_column(String(40), default="issued", nullable=False)
    hosted_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    issued_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    extra_metadata: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)


class ProviderCostRate(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "provider_cost_rates"
    __table_args__ = (
        UniqueConstraint("provider", "service", "operation", "effective_from", name="uq_provider_cost_rate_version"),
    )

    provider: Mapped[str] = mapped_column(String(80), index=True, nullable=False)
    service: Mapped[str] = mapped_column(String(80), index=True, nullable=False)
    operation: Mapped[str] = mapped_column(String(120), index=True, nullable=False)
    pricing_unit: Mapped[str] = mapped_column(String(40), nullable=False)
    input_unit_cost: Mapped[float] = mapped_column(Numeric(20, 12), default=0, nullable=False)
    output_unit_cost: Mapped[float] = mapped_column(Numeric(20, 12), default=0, nullable=False)
    currency: Mapped[str] = mapped_column(String(10), default="USD", nullable=False)
    effective_from: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True, nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, index=True, nullable=False)
    extra_metadata: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)


class ComputeUnitPolicy(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "compute_unit_policies"
    __table_args__ = (
        UniqueConstraint("name", "currency", "effective_from", name="uq_compute_unit_policy_version"),
    )

    name: Mapped[str] = mapped_column(String(80), index=True, nullable=False)
    currency: Mapped[str] = mapped_column(String(10), index=True, nullable=False)
    cost_per_compute_unit: Mapped[float] = mapped_column(Numeric(20, 12), nullable=False)
    effective_from: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True, nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, index=True, nullable=False)
    extra_metadata: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)


class ComputeWallet(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "compute_wallets"
    __table_args__ = (
        UniqueConstraint("user_id", "period_start", "period_end", name="uq_compute_wallet_user_period"),
    )

    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    plan_key: Mapped[str | None] = mapped_column(String(40), index=True, nullable=True)
    period_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True, nullable=False)
    period_end: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True, nullable=False)
    included_cu: Mapped[float | None] = mapped_column(Numeric(20, 9), nullable=True)
    bonus_cu: Mapped[float] = mapped_column(Numeric(20, 9), default=0, nullable=False)
    used_cu: Mapped[float] = mapped_column(Numeric(20, 9), default=0, nullable=False)
    reserved_cu: Mapped[float] = mapped_column(Numeric(20, 9), default=0, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False)

    @property
    def available_cu(self):
        if self.included_cu is None:
            return None
        return self.included_cu + self.bonus_cu - self.used_cu - self.reserved_cu


class ComputeWalletTransaction(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "compute_wallet_transactions"
    __table_args__ = (
        UniqueConstraint("idempotency_key", name="uq_compute_wallet_transaction_idempotency"),
    )

    wallet_id: Mapped[str] = mapped_column(ForeignKey("compute_wallets.id", ondelete="CASCADE"), index=True, nullable=False)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    request_id: Mapped[str | None] = mapped_column(String(120), index=True, nullable=True)
    transaction_type: Mapped[str] = mapped_column(String(30), index=True, nullable=False)
    amount_cu: Mapped[float] = mapped_column(Numeric(20, 9), nullable=False)
    source: Mapped[str] = mapped_column(String(80), index=True, nullable=False)
    reference_id: Mapped[str | None] = mapped_column(String(120), index=True, nullable=True)
    idempotency_key: Mapped[str] = mapped_column(String(220), nullable=False)
    extra_metadata: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)


class UsageEstimate(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "usage_estimates"
    __table_args__ = (
        UniqueConstraint("user_id", "request_id", "capability_key", "estimator_version", name="uq_usage_estimate_request_version"),
    )

    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    request_id: Mapped[str] = mapped_column(String(120), index=True, nullable=False)
    capability_key: Mapped[str] = mapped_column(String(120), index=True, nullable=False)
    context_bucket: Mapped[str] = mapped_column(String(80), index=True, nullable=False)
    estimated_cost: Mapped[float | None] = mapped_column(Numeric(20, 12), nullable=True)
    cost_currency: Mapped[str | None] = mapped_column(String(10), nullable=True)
    estimated_compute_units: Mapped[float | None] = mapped_column(Numeric(20, 9), nullable=True)
    confidence: Mapped[str] = mapped_column(String(20), index=True, nullable=False)
    cost_class: Mapped[str] = mapped_column(String(20), nullable=False)
    status: Mapped[str] = mapped_column(String(30), index=True, nullable=False)
    estimator_version: Mapped[str] = mapped_column(String(20), index=True, nullable=False)
    basis: Mapped[str] = mapped_column(String(80), nullable=False)
    breakdown: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    usage_ledger_id: Mapped[str | None] = mapped_column(ForeignKey("usage_ledger.id", ondelete="SET NULL"), index=True, nullable=True)
    actual_compute_units: Mapped[float | None] = mapped_column(Numeric(20, 9), nullable=True)
    variance_percent: Mapped[float | None] = mapped_column(Numeric(12, 4), nullable=True)


class ResourcePolicy(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "resource_policies"
    __table_args__ = (
        UniqueConstraint("policy_version", "plan_key", "effective_from", name="uq_resource_policy_version_plan"),
    )

    policy_version: Mapped[str] = mapped_column(String(40), index=True, nullable=False)
    plan_key: Mapped[str] = mapped_column(String(40), index=True, nullable=False)
    warning_threshold: Mapped[float] = mapped_column(Numeric(8, 4), nullable=False)
    degrade_threshold: Mapped[float] = mapped_column(Numeric(8, 4), nullable=False)
    hard_compute_threshold: Mapped[float | None] = mapped_column(Numeric(20, 9), nullable=True)
    lite_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    observe_only: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    allow_negative_shadow: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, index=True, nullable=False)
    effective_from: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True, nullable=False)
    extra_metadata: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)


class ResourcePolicyDecision(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "policy_decisions"
    __table_args__ = (
        UniqueConstraint("user_id", "request_id", "capability_key", "policy_version", name="uq_policy_decision_request_version"),
    )

    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    request_id: Mapped[str] = mapped_column(String(120), index=True, nullable=False)
    capability_key: Mapped[str] = mapped_column(String(120), index=True, nullable=False)
    estimate_id: Mapped[str | None] = mapped_column(ForeignKey("usage_estimates.id", ondelete="SET NULL"), index=True, nullable=True)
    decision: Mapped[str] = mapped_column(String(30), index=True, nullable=False)
    reason: Mapped[str] = mapped_column(String(80), nullable=False)
    wallet_available_cu: Mapped[float | None] = mapped_column(Numeric(20, 9), nullable=True)
    estimated_compute_units: Mapped[float | None] = mapped_column(Numeric(20, 9), nullable=True)
    policy_version: Mapped[str] = mapped_column(String(40), index=True, nullable=False)
    execution_mode: Mapped[str] = mapped_column(String(30), nullable=False)
    fallback_mode: Mapped[str | None] = mapped_column(String(30), nullable=True)
    requires_confirmation: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    enforced: Mapped[bool] = mapped_column(Boolean, default=False, index=True, nullable=False)
    requested_execution_mode: Mapped[str | None] = mapped_column(String(30), nullable=True)
    effective_execution_mode: Mapped[str | None] = mapped_column(String(30), index=True, nullable=True)
    fallback_used: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    fallback_capability: Mapped[str | None] = mapped_column(String(120), nullable=True)
    upgrade_prompted: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    response_key: Mapped[str | None] = mapped_column(String(80), nullable=True)
    lite_behavior_version: Mapped[str | None] = mapped_column(String(30), nullable=True)
    rollout_mode: Mapped[str | None] = mapped_column(String(30), nullable=True)
    extra_metadata: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)


class UsageLedger(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "usage_ledger"
    __table_args__ = (UniqueConstraint("idempotency_key", name="uq_usage_ledger_idempotency_key"),)

    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    subscription_id: Mapped[str | None] = mapped_column(ForeignKey("subscriptions.id", ondelete="SET NULL"), nullable=True)
    plan_id: Mapped[str | None] = mapped_column(ForeignKey("plans.id", ondelete="SET NULL"), nullable=True)
    action_type: Mapped[str] = mapped_column(String(80), index=True, nullable=False)
    operation: Mapped[str] = mapped_column(String(120), default="unknown", index=True, nullable=False)
    provider: Mapped[str | None] = mapped_column(String(80), index=True, nullable=True)
    model: Mapped[str | None] = mapped_column(String(160), nullable=True)
    status: Mapped[str] = mapped_column(String(30), default="completed", index=True, nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    input_tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    embedding_tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    voice_seconds: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    voice_input_seconds: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    voice_output_seconds: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    web_searches: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    image_generations: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    tool_calls: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    estimated_cost: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    actual_cost: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    cost_currency: Mapped[str | None] = mapped_column(String(10), nullable=True)
    pricing_status: Mapped[str] = mapped_column(String(30), default="unpriced", index=True, nullable=False)
    pricing_rate_id: Mapped[str | None] = mapped_column(ForeignKey("provider_cost_rates.id", ondelete="SET NULL"), nullable=True)
    compute_units: Mapped[float | None] = mapped_column(Numeric(20, 9), nullable=True)
    compute_unit_status: Mapped[str] = mapped_column(String(30), default="unpriced", index=True, nullable=False)
    compute_unit_policy_id: Mapped[str | None] = mapped_column(ForeignKey("compute_unit_policies.id", ondelete="SET NULL"), nullable=True)
    capability_key: Mapped[str | None] = mapped_column(String(120), index=True, nullable=True)
    capability_category: Mapped[str | None] = mapped_column(String(80), index=True, nullable=True)
    execution_type: Mapped[str | None] = mapped_column(String(30), index=True, nullable=True)
    request_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    idempotency_key: Mapped[str | None] = mapped_column(String(180), nullable=True)
    extra_metadata: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)


class UsageCounter(Base):
    __tablename__ = "usage_counters"
    __table_args__ = (UniqueConstraint("user_id", "entitlement_key", "period_start", "period_end", name="uq_usage_counter_period"),)

    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    entitlement_key: Mapped[str] = mapped_column(String(80), primary_key=True)
    period_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), primary_key=True)
    period_end: Mapped[datetime] = mapped_column(DateTime(timezone=True), primary_key=True)
    used_quantity: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False)


class Institution(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "institutions"

    name: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    code: Mapped[str] = mapped_column(String(80), unique=True, index=True, nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class InstitutionDomain(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "institution_domains"
    __table_args__ = (UniqueConstraint("domain", name="uq_institution_domain"),)

    institution_id: Mapped[str] = mapped_column(ForeignKey("institutions.id", ondelete="CASCADE"), index=True, nullable=False)
    domain: Mapped[str] = mapped_column(String(255), index=True, nullable=False)
    status: Mapped[str] = mapped_column(String(40), default="approved", nullable=False)
    instant_approval_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    approved_by: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class StudentVerification(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "student_verifications"

    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    institution_id: Mapped[str | None] = mapped_column(ForeignKey("institutions.id", ondelete="SET NULL"), nullable=True)
    institutional_email: Mapped[str | None] = mapped_column(String(255), index=True, nullable=True)
    verification_method: Mapped[str | None] = mapped_column(String(40), nullable=True)
    status: Mapped[str] = mapped_column(String(40), default="not_started", index=True, nullable=False)
    document_file_id: Mapped[str | None] = mapped_column(ForeignKey("files.id", ondelete="SET NULL"), nullable=True)
    otp_requested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    rejection_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    reviewed_by: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False)


class VerificationAttempt(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "verification_attempts"

    verification_id: Mapped[str] = mapped_column(ForeignKey("student_verifications.id", ondelete="CASCADE"), index=True, nullable=False)
    method: Mapped[str] = mapped_column(String(40), nullable=False)
    email_hash: Mapped[str | None] = mapped_column(String(128), index=True, nullable=True)
    ip_hash: Mapped[str | None] = mapped_column(String(128), index=True, nullable=True)
    result: Mapped[str] = mapped_column(String(40), nullable=False)
    failure_reason: Mapped[str | None] = mapped_column(Text, nullable=True)


class BillingEvent(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "billing_events"
    __table_args__ = (UniqueConstraint("provider", "provider_event_id", name="uq_billing_provider_event"),)

    provider: Mapped[str] = mapped_column(String(40), nullable=False)
    provider_event_id: Mapped[str] = mapped_column(String(255), nullable=False)
    event_type: Mapped[str] = mapped_column(String(80), nullable=False)
    signature_verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    payload_hash: Mapped[str | None] = mapped_column(String(128), nullable=True)
    processing_status: Mapped[str] = mapped_column(String(40), default="pending", nullable=False)
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    failure_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
