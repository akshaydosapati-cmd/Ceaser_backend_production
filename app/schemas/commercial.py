from datetime import datetime

from pydantic import BaseModel, EmailStr, Field

from app.schemas.common import ORMModel, TimestampedModel


class PlanRead(TimestampedModel):
    code: str
    name: str
    description: str
    currency: str
    monthly_price: int
    annual_price: int
    active: bool
    public: bool


class EntitlementRead(TimestampedModel):
    plan_id: str
    entitlement_key: str
    limit_value: int
    value_type: str
    reset_period: str
    extra_metadata: dict


class UsageSummaryItem(BaseModel):
    entitlement_key: str
    limit_value: int
    used_quantity: int
    remaining: int
    reset_period: str


class SubscriptionRead(TimestampedModel):
    user_id: str
    plan_id: str
    provider: str
    status: str
    billing_interval: str
    current_period_start: datetime | None = None
    current_period_end: datetime | None = None
    cancel_at_period_end: bool


class StudentVerificationRead(TimestampedModel):
    user_id: str
    institution_id: str | None = None
    institutional_email: str | None = None
    verification_method: str | None = None
    status: str
    document_file_id: str | None = None
    verified_at: datetime | None = None
    expires_at: datetime | None = None
    rejection_reason: str | None = None
    reviewed_at: datetime | None = None


class CommercialOverview(BaseModel):
    plan: PlanRead
    subscription: SubscriptionRead | None
    student_verification: StudentVerificationRead | None
    entitlements: list[EntitlementRead]
    usage: list[UsageSummaryItem]
    student_pricing_available: bool


class StudentEmailStartRequest(BaseModel):
    institutional_email: EmailStr


class StudentEmailStartResponse(BaseModel):
    status: str
    message: str
    verification_id: str | None = None


class StudentEmailConfirmRequest(BaseModel):
    verification_id: str
    otp: str = Field(min_length=6, max_length=6)


class StudentDocumentRequest(BaseModel):
    document_file_id: str
    institution_code: str = "NHCE"


class CheckoutRequest(BaseModel):
    plan_code: str
    billing_interval: str = "monthly"


class CheckoutResponse(BaseModel):
    provider: str
    checkout_id: str
    status: str
    message: str


class EntitlementDecision(BaseModel):
    allowed: bool
    entitlement_key: str
    limit_value: int | None = None
    used_quantity: int = 0
    remaining: int | None = None
    user_message: str


class UsageRecordRequest(BaseModel):
    action_type: str
    quantity: int = Field(default=1, ge=1)
    input_tokens: int = 0
    output_tokens: int = 0
    embedding_tokens: int = 0
    voice_seconds: int = 0
    estimated_cost: float = 0
    request_id: str | None = None
    metadata: dict = Field(default_factory=dict)


class BillingEventCreate(BaseModel):
    provider_event_id: str
    event_type: str
    signature_verified: bool = True
    payload_hash: str | None = None
    payload: dict = Field(default_factory=dict)
