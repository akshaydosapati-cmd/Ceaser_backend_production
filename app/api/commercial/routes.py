from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.core.database.session import get_db
from app.core.security.dependencies import get_current_user
from app.models.commercial import Plan
from app.models.user import User
from app.schemas.commercial import (
    BillingEventCreate,
    CheckoutRequest,
    CheckoutResponse,
    CommercialOverview,
    EntitlementDecision,
    PlanRead,
    StudentDocumentRequest,
    StudentEmailConfirmRequest,
    StudentEmailStartRequest,
    StudentEmailStartResponse,
    StudentVerificationRead,
    UsageRecordRequest,
)
from app.services.commercial_service import BillingService, PlanService, StudentVerificationService, SubscriptionService, UsageService

router = APIRouter(prefix="/commercial", tags=["commercial"])


@router.get("/plans", response_model=list[PlanRead])
def list_plans(db: Annotated[Session, Depends(get_db)]):
    return PlanService(db).public_plans()


@router.get("/me", response_model=CommercialOverview)
def commercial_overview(user: Annotated[User, Depends(get_current_user)], db: Annotated[Session, Depends(get_db)]):
    subscription = SubscriptionService(db).active_subscription(user.id)
    plans = PlanService(db)
    plan = db.query(Plan).filter_by(id=subscription.plan_id).first()
    if not plan:
        plan = plans.get_by_code("FREE")
    verification = StudentVerificationService(db).current(user.id)
    return {
        "plan": plan,
        "subscription": subscription,
        "student_verification": verification,
        "entitlements": plans.entitlements(subscription.plan_id),
        "usage": UsageService(db).summary(user.id),
        "student_pricing_available": StudentVerificationService(db).is_student_pricing_available(user.id),
    }


@router.post("/student/email/start", response_model=StudentEmailStartResponse)
def start_student_email_verification(
    payload: StudentEmailStartRequest,
    request: Request,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
):
    try:
        verification = StudentVerificationService(db).start_email(user.id, str(payload.institutional_email), request.client.host if request.client else None)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    if verification.status == "document_required":
        return {
            "status": verification.status,
            "verification_id": verification.id,
            "message": "Instant verification is currently available only for approved NHCE student accounts. Use student document verification instead.",
        }
    return {
        "status": verification.status,
        "verification_id": verification.id,
        "message": "Verification started. Supabase OTP delivery should send a six-digit code to the institutional email.",
    }


@router.post("/student/email/confirm", response_model=StudentVerificationRead)
def confirm_student_email_verification(
    payload: StudentEmailConfirmRequest,
    request: Request,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
):
    try:
        return StudentVerificationService(db).confirm_email(user.id, payload.verification_id, payload.otp, request.client.host if request.client else None)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.post("/student/document", response_model=StudentVerificationRead)
def submit_student_document(
    payload: StudentDocumentRequest,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
):
    try:
        return StudentVerificationService(db).submit_document(user.id, payload.document_file_id, payload.institution_code)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.get("/student/status", response_model=StudentVerificationRead | None)
def student_status(user: Annotated[User, Depends(get_current_user)], db: Annotated[Session, Depends(get_db)]):
    return StudentVerificationService(db).current(user.id)


@router.get("/entitlements/{action}", response_model=EntitlementDecision)
def check_entitlement(action: str, user: Annotated[User, Depends(get_current_user)], db: Annotated[Session, Depends(get_db)], quantity: int = 1):
    decision = UsageService(db).authorize(user.id, action, quantity)
    return decision.__dict__


@router.post("/usage")
def record_usage(payload: UsageRecordRequest, user: Annotated[User, Depends(get_current_user)], db: Annotated[Session, Depends(get_db)]):
    decision = UsageService(db).authorize(user.id, payload.action_type, payload.quantity)
    if not decision.allowed:
        raise HTTPException(status_code=status.HTTP_402_PAYMENT_REQUIRED, detail=decision.user_message)
    ledger = UsageService(db).record(
        user.id,
        payload.action_type,
        payload.quantity,
        extra_metadata=payload.metadata,
    )
    return {"id": ledger.id, "status": "recorded"}


@router.post("/checkout/test", response_model=CheckoutResponse)
def create_test_checkout(payload: CheckoutRequest, user: Annotated[User, Depends(get_current_user)], db: Annotated[Session, Depends(get_db)]):
    try:
        return BillingService(db).create_test_checkout(user.id, payload.plan_code, payload.billing_interval)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.post("/billing/test-event")
def record_test_billing_event(payload: BillingEventCreate, user: Annotated[User, Depends(get_current_user)], db: Annotated[Session, Depends(get_db)]):
    event = BillingService(db).record_event("test", payload.provider_event_id, payload.event_type, payload.signature_verified, payload.payload_hash)
    return {"id": event.id, "status": event.processing_status}
