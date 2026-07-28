from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy.orm import Session

from app.core.database.session import get_db
from app.core.security.dependencies import get_current_user
from app.models.user import User
from app.schemas.commercial import (
    BillingCreateOrderRequest,
    BillingCreateOrderResponse,
    BillingCreateSubscriptionRequest,
    BillingCreateSubscriptionResponse,
    BillingInvoiceRead,
    BillingManageResponse,
    BillingSubscriptionOverview,
    BillingVerifyPaymentRequest,
    BillingVerifyPaymentResponse,
)
from app.services.billing_service import BillingConfigurationError, BillingProviderError, FeatureAccessService, RazorpayBillingService


router = APIRouter(prefix="/billing", tags=["billing"])


@router.post("/create-order", response_model=BillingCreateOrderResponse)
def create_order(
    payload: BillingCreateOrderRequest,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
):
    try:
        return RazorpayBillingService(db).create_order(
            user,
            amount=payload.amount,
            currency=payload.currency,
            receipt=payload.receipt,
            plan_code=payload.plan_code,
            billing_interval=payload.billing_interval,
        )
    except BillingConfigurationError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except BillingProviderError as exc:
        status_code = status.HTTP_401_UNAUTHORIZED if exc.category == "authentication" else status.HTTP_502_BAD_GATEWAY
        raise HTTPException(status_code=status_code, detail="Could not create the payment order.") from exc


@router.post("/create-subscription", response_model=BillingCreateSubscriptionResponse)
def create_subscription(
    payload: BillingCreateSubscriptionRequest,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
):
    try:
        return RazorpayBillingService(db).create_subscription(user, plan_code=payload.plan_code, billing_interval=payload.billing_interval)
    except (BillingConfigurationError, ValueError) as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except BillingProviderError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Payment provider is temporarily unavailable.") from exc


@router.post("/verify-payment", response_model=BillingVerifyPaymentResponse)
def verify_payment(
    payload: BillingVerifyPaymentRequest,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
):
    try:
        subscription = RazorpayBillingService(db).verify_payment(
            user,
            payment_id=payload.razorpay_payment_id,
            order_id=payload.razorpay_order_id,
            subscription_id=payload.razorpay_subscription_id,
            signature=payload.razorpay_signature,
        )
        return {
            "status": "verified",
            "message": "Payment verified. Subscription status refreshed.",
            "subscription": subscription,
        }
    except BillingProviderError as exc:
        code = status.HTTP_400_BAD_REQUEST if exc.category == "invalid_signature" else status.HTTP_502_BAD_GATEWAY
        raise HTTPException(status_code=code, detail="Payment verification failed.") from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.post("/webhook")
async def billing_webhook(request: Request, db: Annotated[Session, Depends(get_db)]):
    raw_body = await request.body()
    signature = request.headers.get("x-razorpay-signature")
    try:
        event = RazorpayBillingService(db).process_webhook(raw_body, signature)
        return {"status": "processed", "event_id": event.provider_event_id}
    except BillingProviderError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid billing webhook.") from exc


@router.get("/subscription", response_model=BillingSubscriptionOverview)
def billing_subscription(user: Annotated[User, Depends(get_current_user)], db: Annotated[Session, Depends(get_db)]):
    overview = RazorpayBillingService(db).overview(user.id)
    overview["feature_access"] = FeatureAccessService(db).snapshot(user.id).__dict__
    return overview


@router.get("/invoices", response_model=list[BillingInvoiceRead])
def billing_invoices(user: Annotated[User, Depends(get_current_user)], db: Annotated[Session, Depends(get_db)]):
    return RazorpayBillingService(db).invoices(user.id)


@router.post("/cancel", response_model=BillingManageResponse)
def cancel_subscription(user: Annotated[User, Depends(get_current_user)], db: Annotated[Session, Depends(get_db)]):
    try:
        subscription = RazorpayBillingService(db).cancel(user.id)
        return {"status": "cancelled", "message": "Subscription will stop at the end of the current billing cycle.", "subscription": subscription}
    except (ValueError, BillingConfigurationError) as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except BillingProviderError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Could not cancel the subscription right now.") from exc


@router.post("/resume", response_model=BillingManageResponse)
def resume_subscription(user: Annotated[User, Depends(get_current_user)], db: Annotated[Session, Depends(get_db)]):
    try:
        subscription = RazorpayBillingService(db).resume(user.id)
        return {"status": "resumed", "message": "Subscription resumed successfully.", "subscription": subscription}
    except (ValueError, BillingConfigurationError) as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except BillingProviderError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Could not resume the subscription right now.") from exc
