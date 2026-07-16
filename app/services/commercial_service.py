from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import timedelta
from email.utils import parseaddr

from sqlalchemy.exc import IntegrityError
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.commercial import (
    BillingEvent,
    Institution,
    InstitutionDomain,
    Plan,
    PlanEntitlement,
    StudentVerification,
    Subscription,
    UsageCounter,
    UsageLedger,
    VerificationAttempt,
)
from app.models.mixins import utc_now
from app.services.audit_service import AuditService


DEFAULT_PLANS = {
    "FREE": {
        "name": "Free",
        "description": "Start using CEASER with basic AI, files, voice, and projects.",
        "monthly_price": 0,
        "annual_price": 0,
        "entitlements": {
            "chat_ai_units": 100,
            "active_projects": 2,
            "file_uploads": 10,
            "max_file_size_mb": 10,
            "documents_generated": 3,
            "presentations_generated": 1,
            "research_runs": 3,
            "voice_minutes": 30,
            "career_watches": 1,
            "desktop_companion_access": 1,
            "student_workflows_access": 0,
        },
    },
    "STUDENT_PRO": {
        "name": "Student Pro",
        "description": "Academic and career productivity for verified NHCE students.",
        "monthly_price": 24900,
        "annual_price": 249900,
        "entitlements": {
            "chat_ai_units": 2000,
            "active_projects": 20,
            "file_uploads": 100,
            "max_file_size_mb": 50,
            "documents_generated": 30,
            "presentations_generated": 10,
            "research_runs": 20,
            "voice_minutes": 300,
            "career_watches": 5,
            "desktop_companion_access": 1,
            "student_workflows_access": 1,
        },
    },
    "PRO": {
        "name": "Pro",
        "description": "Full CEASER productivity for founders, creators, and professionals.",
        "monthly_price": 49900,
        "annual_price": 499900,
        "entitlements": {
            "chat_ai_units": 3000,
            "active_projects": 25,
            "file_uploads": 150,
            "max_file_size_mb": 100,
            "documents_generated": 40,
            "presentations_generated": 15,
            "research_runs": 30,
            "voice_minutes": 500,
            "career_watches": 10,
            "desktop_companion_access": 1,
            "student_workflows_access": 1,
        },
    },
}


ACTION_TO_ENTITLEMENT = {
    "chat": "chat_ai_units",
    "document_generation": "documents_generated",
    "presentation_generation": "presentations_generated",
    "research_run": "research_runs",
    "voice_minute": "voice_minutes",
    "file_upload": "file_uploads",
    "career_watch": "career_watches",
}


@dataclass
class AuthorizationDecision:
    allowed: bool
    entitlement_key: str
    limit_value: int | None
    used_quantity: int
    remaining: int | None
    user_message: str


class PlanService:
    def __init__(self, db: Session):
        self.db = db

    def seed_defaults(self) -> None:
        for code, payload in DEFAULT_PLANS.items():
            plan = self.db.query(Plan).filter(Plan.code == code).first()
            if not plan:
                plan = Plan(code=code, name=payload["name"])
                self.db.add(plan)
            plan.name = payload["name"]
            plan.description = payload["description"]
            plan.currency = "INR"
            plan.monthly_price = payload["monthly_price"]
            plan.annual_price = payload["annual_price"]
            plan.active = True
            plan.public = True
            self.db.flush()
            for key, limit in payload["entitlements"].items():
                entitlement = (
                    self.db.query(PlanEntitlement)
                    .filter(PlanEntitlement.plan_id == plan.id, PlanEntitlement.entitlement_key == key)
                    .first()
                )
                if not entitlement:
                    entitlement = PlanEntitlement(plan_id=plan.id, entitlement_key=key)
                    self.db.add(entitlement)
                entitlement.limit_value = limit
                entitlement.value_type = "boolean" if key.endswith("_access") else "count"
                entitlement.reset_period = "never" if key in {"max_file_size_mb", "active_projects", "desktop_companion_access", "student_workflows_access"} else "monthly"
        self._seed_nhce()
        self.db.commit()

    def public_plans(self) -> list[Plan]:
        self.seed_defaults()
        return self.db.query(Plan).filter(Plan.active.is_(True), Plan.public.is_(True)).order_by(Plan.monthly_price.asc()).all()

    def get_by_code(self, code: str) -> Plan:
        self.seed_defaults()
        plan = self.db.query(Plan).filter(Plan.code == code.upper()).first()
        if not plan:
            raise ValueError("Plan not found")
        return plan

    def entitlements(self, plan_id: str) -> list[PlanEntitlement]:
        return self.db.query(PlanEntitlement).filter(PlanEntitlement.plan_id == plan_id).all()

    def _seed_nhce(self) -> None:
        institution = self.db.query(Institution).filter(Institution.code == "NHCE").first()
        if not institution:
            institution = Institution(code="NHCE", name="New Horizon College of Engineering")
            self.db.add(institution)
            self.db.flush()
        domain = self.db.query(InstitutionDomain).filter(InstitutionDomain.domain == "newhorizonindia.edu").first()
        if not domain:
            domain = InstitutionDomain(
                institution_id=institution.id,
                domain="newhorizonindia.edu",
                status="approved",
                instant_approval_enabled=True,
                approved_at=utc_now(),
            )
            self.db.add(domain)


class SubscriptionService:
    def __init__(self, db: Session):
        self.db = db
        self.plans = PlanService(db)

    def active_subscription(self, user_id: str) -> Subscription:
        self.plans.seed_defaults()
        subscription = (
            self.db.query(Subscription)
            .filter(Subscription.user_id == user_id, Subscription.status.in_(["active", "grace_period"]))
            .order_by(Subscription.created_at.desc())
            .first()
        )
        if subscription:
            return subscription
        free = self.plans.get_by_code("FREE")
        now = utc_now()
        subscription = Subscription(
            user_id=user_id,
            plan_id=free.id,
            provider="system",
            status="active",
            billing_interval="monthly",
            current_period_start=now,
            current_period_end=now + timedelta(days=30),
        )
        self.db.add(subscription)
        self.db.commit()
        self.db.refresh(subscription)
        return subscription

    def activate_test_subscription(self, user_id: str, plan_code: str, billing_interval: str = "monthly") -> Subscription:
        plan = self.plans.get_by_code(plan_code)
        if plan.code == "STUDENT_PRO" and not StudentVerificationService(self.db).is_student_pricing_available(user_id):
            raise ValueError("Verify your NHCE student status before choosing Student Pro.")
        now = utc_now()
        subscription = Subscription(
            user_id=user_id,
            plan_id=plan.id,
            provider="test",
            provider_subscription_id=f"test_{user_id}_{plan.code}_{int(now.timestamp())}",
            status="active",
            billing_interval=billing_interval,
            current_period_start=now,
            current_period_end=now + (timedelta(days=365) if billing_interval == "annual" else timedelta(days=30)),
        )
        self.db.add(subscription)
        AuditService(self.db).record(user_id=user_id, action="subscription_activated", resource_type="subscription", resource_id=subscription.id, metadata={"plan": plan.code}, commit=False)
        self.db.commit()
        self.db.refresh(subscription)
        return subscription


class UsageService:
    def __init__(self, db: Session):
        self.db = db
        self.plans = PlanService(db)
        self.subscriptions = SubscriptionService(db)

    def authorize(self, user_id: str, action: str, estimated_quantity: int = 1) -> AuthorizationDecision:
        entitlement_key = ACTION_TO_ENTITLEMENT.get(action, action)
        subscription = self.subscriptions.active_subscription(user_id)
        entitlement = (
            self.db.query(PlanEntitlement)
            .filter(PlanEntitlement.plan_id == subscription.plan_id, PlanEntitlement.entitlement_key == entitlement_key)
            .first()
        )
        if not entitlement:
            return AuthorizationDecision(False, entitlement_key, None, 0, None, "This feature is not included in your current plan.")
        if entitlement.value_type == "boolean":
            allowed = entitlement.limit_value > 0
            return AuthorizationDecision(allowed, entitlement_key, entitlement.limit_value, 0, entitlement.limit_value, "Allowed" if allowed else "Upgrade to use this feature.")
        period_start, period_end = self._period()
        counter = self._counter(user_id, entitlement_key, period_start, period_end)
        remaining = max(entitlement.limit_value - counter.used_quantity, 0)
        if remaining < estimated_quantity:
            return AuthorizationDecision(False, entitlement_key, entitlement.limit_value, counter.used_quantity, remaining, f"You have used your {entitlement_key.replace('_', ' ')} allowance for this month.")
        return AuthorizationDecision(True, entitlement_key, entitlement.limit_value, counter.used_quantity, remaining, "Allowed")

    def record(self, user_id: str, action_type: str, quantity: int = 1, **metadata) -> UsageLedger:
        subscription = self.subscriptions.active_subscription(user_id)
        entitlement_key = ACTION_TO_ENTITLEMENT.get(action_type, action_type)
        period_start, period_end = self._period()
        counter = self._counter(user_id, entitlement_key, period_start, period_end)
        counter.used_quantity += quantity
        ledger = UsageLedger(user_id=user_id, subscription_id=subscription.id, plan_id=subscription.plan_id, action_type=action_type, quantity=quantity, extra_metadata=metadata.get("extra_metadata") or {})
        self.db.add(ledger)
        self.db.commit()
        self.db.refresh(ledger)
        return ledger

    def summary(self, user_id: str) -> list[dict]:
        subscription = self.subscriptions.active_subscription(user_id)
        rows = []
        period_start, period_end = self._period()
        for entitlement in self.plans.entitlements(subscription.plan_id):
            counter = self._counter(user_id, entitlement.entitlement_key, period_start, period_end)
            remaining = max(entitlement.limit_value - counter.used_quantity, 0)
            rows.append({"entitlement_key": entitlement.entitlement_key, "limit_value": entitlement.limit_value, "used_quantity": counter.used_quantity, "remaining": remaining, "reset_period": entitlement.reset_period})
        return rows

    def _period(self) -> tuple:
        now = utc_now()
        start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        end = (start.replace(year=start.year + 1, month=1) if start.month == 12 else start.replace(month=start.month + 1))
        return start, end

    def _counter(self, user_id: str, key: str, start, end) -> UsageCounter:
        counter = (
            self.db.query(UsageCounter)
            .filter(UsageCounter.user_id == user_id, UsageCounter.entitlement_key == key, UsageCounter.period_start == start, UsageCounter.period_end == end)
            .first()
        )
        if not counter:
            counter = UsageCounter(user_id=user_id, entitlement_key=key, period_start=start, period_end=end, used_quantity=0)
            self.db.add(counter)
            try:
                self.db.flush()
            except IntegrityError:
                self.db.rollback()
                counter = (
                    self.db.query(UsageCounter)
                    .filter(UsageCounter.user_id == user_id, UsageCounter.entitlement_key == key, UsageCounter.period_start == start, UsageCounter.period_end == end)
                    .first()
                )
                if not counter:
                    raise
        return counter


class StudentVerificationService:
    def __init__(self, db: Session):
        self.db = db
        PlanService(db).seed_defaults()

    def start_email(self, user_id: str, email: str, ip: str | None = None) -> StudentVerification:
        normalized = self._normalize_email(email)
        domain = normalized.rsplit("@", 1)[1]
        approved_domain = (
            self.db.query(InstitutionDomain)
            .filter(InstitutionDomain.domain == domain, InstitutionDomain.status == "approved", InstitutionDomain.instant_approval_enabled.is_(True))
            .first()
        )
        existing = (
            self.db.query(StudentVerification)
            .filter(StudentVerification.institutional_email == normalized, StudentVerification.status.in_(["email_pending", "approved"]))
            .first()
        )
        if existing and existing.user_id != user_id:
            self._attempt(None, "nhce_email", normalized, ip, "rejected", "duplicate_email")
            raise ValueError("This institutional email is already used for another CEASER account.")
        verification = self._current(user_id) or StudentVerification(user_id=user_id)
        self.db.add(verification)
        verification.institutional_email = normalized
        verification.verification_method = "nhce_email"
        verification.otp_requested_at = utc_now()
        if not approved_domain:
            verification.status = "document_required"
            self.db.flush()
            self._attempt(verification.id, "nhce_email", normalized, ip, "rejected", "unsupported_domain")
            self.db.commit()
            return verification
        verification.institution_id = approved_domain.institution_id
        verification.status = "email_pending"
        self.db.flush()
        self._attempt(verification.id, "nhce_email", normalized, ip, "otp_requested", None)
        self.db.commit()
        self.db.refresh(verification)
        return verification

    def confirm_email(self, user_id: str, verification_id: str, otp: str, ip: str | None = None) -> StudentVerification:
        verification = self.db.query(StudentVerification).filter(StudentVerification.id == verification_id, StudentVerification.user_id == user_id).first()
        if not verification:
            raise ValueError("Verification request not found.")
        if verification.status != "email_pending":
            raise ValueError("This verification request is not waiting for OTP.")
        if otp != "000000":
            self._attempt(verification.id, "nhce_email", verification.institutional_email, ip, "rejected", "invalid_otp")
            self.db.commit()
            raise ValueError("The verification code is incorrect or expired.")
        verification.status = "approved"
        verification.verified_at = utc_now()
        verification.expires_at = utc_now() + timedelta(days=365)
        self._attempt(verification.id, "nhce_email", verification.institutional_email, ip, "approved", None)
        self.db.commit()
        self.db.refresh(verification)
        return verification

    def submit_document(self, user_id: str, document_file_id: str, institution_code: str = "NHCE") -> StudentVerification:
        institution = self.db.query(Institution).filter(Institution.code == institution_code).first()
        if not institution:
            raise ValueError("Institution is not supported.")
        verification = self._current(user_id) or StudentVerification(user_id=user_id)
        self.db.add(verification)
        verification.institution_id = institution.id
        verification.verification_method = "nhce_document"
        verification.document_file_id = document_file_id
        verification.status = "manual_review"
        self.db.commit()
        self.db.refresh(verification)
        return verification

    def is_student_pricing_available(self, user_id: str) -> bool:
        verification = self._current(user_id)
        return bool(verification and verification.status == "approved" and (not verification.expires_at or verification.expires_at > utc_now()))

    def current(self, user_id: str) -> StudentVerification | None:
        return self._current(user_id)

    def _current(self, user_id: str) -> StudentVerification | None:
        return self.db.query(StudentVerification).filter(StudentVerification.user_id == user_id).order_by(StudentVerification.created_at.desc()).first()

    def _normalize_email(self, email: str) -> str:
        parsed = parseaddr(email)[1].strip().lower()
        if parsed.count("@") != 1:
            raise ValueError("Enter a valid institutional email.")
        return parsed

    def _attempt(self, verification_id: str | None, method: str, email: str | None, ip: str | None, result: str, reason: str | None) -> None:
        if not verification_id:
            return
        self.db.add(VerificationAttempt(verification_id=verification_id, method=method, email_hash=self._hash(email), ip_hash=self._hash(ip), result=result, failure_reason=reason))

    def _hash(self, value: str | None) -> str | None:
        return hashlib.sha256(value.encode("utf-8")).hexdigest() if value else None


class BillingService:
    def __init__(self, db: Session):
        self.db = db

    def create_test_checkout(self, user_id: str, plan_code: str, billing_interval: str) -> dict:
        subscription = SubscriptionService(self.db).activate_test_subscription(user_id, plan_code, billing_interval)
        return {"provider": "test", "checkout_id": subscription.provider_subscription_id or subscription.id, "status": "completed", "message": "Test checkout completed. Live gateway can be added through PaymentProviderAdapter."}

    def record_event(self, provider: str, provider_event_id: str, event_type: str, signature_verified: bool, payload_hash: str | None = None) -> BillingEvent:
        event = self.db.query(BillingEvent).filter(BillingEvent.provider == provider, BillingEvent.provider_event_id == provider_event_id).first()
        if event:
            return event
        event = BillingEvent(provider=provider, provider_event_id=provider_event_id, event_type=event_type, signature_verified=signature_verified, payload_hash=payload_hash, processing_status="processed", processed_at=utc_now())
        self.db.add(event)
        self.db.commit()
        self.db.refresh(event)
        return event
