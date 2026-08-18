from typing import Annotated
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from app.core.database.session import get_db
from app.core.security.dependencies import get_current_user
from app.models.user import User
from app.schemas.credits import CreditReservationRequest, CreditSettlementRequest, PurchaseOrderRequest, PurchaseVerifyRequest, ReferralApplyRequest
from app.services.billing_service import BillingProviderError
from app.services.credit_service import CreditService, InsufficientCreditsError

router = APIRouter(prefix="/credits", tags=["credits"])

@router.get("/overview")
def overview(user: Annotated[User, Depends(get_current_user)], db: Annotated[Session, Depends(get_db)]):
    return CreditService(db).overview(user.id)

@router.get("/products")
def products(user: Annotated[User, Depends(get_current_user)], db: Annotated[Session, Depends(get_db)]):
    service = CreditService(db)
    return [{"id": p.id, "code": p.code, "name": p.name, "credits": p.credits, "amount_inr": p.amount_inr} for p in service.products(service.plan_code(user.id))]

@router.post("/reserve")
def reserve(payload: CreditReservationRequest, user: Annotated[User, Depends(get_current_user)], db: Annotated[Session, Depends(get_db)]):
    try:
        row = CreditService(db).reserve(user.id, payload.request_id, payload.workload, payload.estimate)
        return {"status": row.status, "reservation_id": row.id, "estimated_credits": row.estimated_credits}
    except InsufficientCreditsError as exc:
        raise HTTPException(status_code=status.HTTP_402_PAYMENT_REQUIRED, detail={"code": "insufficient_credits", "message": "You're out of CEASER credits."}) from exc

@router.post("/settle")
def settle(payload: CreditSettlementRequest, user: Annotated[User, Depends(get_current_user)], db: Annotated[Session, Depends(get_db)]):
    row = CreditService(db).settle(user.id, payload.request_id, payload.actual, meaningful_output=payload.meaningful_output)
    return {"status": row.status, "settled_credits": row.settled_credits}

@router.post("/release/{request_id}")
def release(request_id: str, user: Annotated[User, Depends(get_current_user)], db: Annotated[Session, Depends(get_db)]):
    row = CreditService(db).release(user.id, request_id)
    return {"status": row.status if row else "not_found"}

@router.post("/referrals/apply")
def apply_referral(payload: ReferralApplyRequest, user: Annotated[User, Depends(get_current_user)], db: Annotated[Session, Depends(get_db)]):
    try:
        return {"status": CreditService(db).apply_referral(user, payload.code).status}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

@router.post("/purchases/order")
def purchase_order(payload: PurchaseOrderRequest, user: Annotated[User, Depends(get_current_user)], db: Annotated[Session, Depends(get_db)]):
    try:
        return CreditService(db).create_purchase_order(user, payload.product_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

@router.post("/purchases/verify")
def verify_purchase(payload: PurchaseVerifyRequest, user: Annotated[User, Depends(get_current_user)], db: Annotated[Session, Depends(get_db)]):
    try:
        row = CreditService(db).verify_purchase(user.id, payload.order_id, payload.payment_id, payload.signature)
        return {"status": row.status, "credits": row.credits}
    except (ValueError, BillingProviderError) as exc:
        raise HTTPException(status_code=400, detail="Credit payment verification failed.") from exc
