from __future__ import annotations

import secrets
from datetime import timedelta, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.core.config.settings import settings
from app.models.commercial import Plan, Subscription
from app.models.growth import CreditLedger, CreditProduct, CreditPurchase, CreditReservation, CreditWallet, Referral, ReferralCode
from app.models.mixins import utc_now
from app.models.user import User
from app.services.billing_service import BillingProviderError, RazorpayGateway


class InsufficientCreditsError(ValueError):
    pass


class CreditService:
    def __init__(self, db: Session):
        self.db = db

    def plan_code(self, user_id: str) -> str:
        row = (self.db.query(Subscription, Plan).join(Plan, Plan.id == Subscription.plan_id).filter(Subscription.user_id == user_id, Subscription.status.in_(["active", "grace_period", "authenticated"])).order_by(Subscription.created_at.desc()).first())
        return str(row[1].code if row else "FREE").upper()

    def wallet(self, user_id: str, *, lock: bool = False) -> CreditWallet:
        query = self.db.query(CreditWallet).filter(CreditWallet.user_id == user_id)
        row = query.with_for_update().first() if lock else query.first()
        plan = self.plan_code(user_id)
        allowance = settings.credit_pro_monthly if plan in {"PRO", "STUDENT_PRO"} else settings.credit_free_monthly
        now = utc_now()
        if not row:
            row = CreditWallet(user_id=user_id, plan=plan, monthly_balance=allowance, cycle_start=now, cycle_end=now + timedelta(days=30))
            self.db.add(row)
            self.db.flush()
            self._ledger(row, allowance, "MONTHLY", "monthly_grant", "plan_allowance", f"initial:{row.cycle_start.date()}")
        elif (row.cycle_end.replace(tzinfo=timezone.utc) if row.cycle_end.tzinfo is None else row.cycle_end) <= now or row.plan != plan:
            row.plan, row.monthly_balance, row.cycle_start, row.cycle_end = plan, allowance, now, now + timedelta(days=30)
            self._ledger(row, allowance, "MONTHLY", "monthly_grant", "plan_allowance", f"renewal:{row.cycle_start.date()}")
        return row

    def overview(self, user_id: str) -> dict[str, Any]:
        wallet = self.wallet(user_id)
        code = self.referral_code(user_id)
        recent = self.db.query(CreditLedger).filter(CreditLedger.user_id == user_id).order_by(CreditLedger.created_at.desc()).limit(25).all()
        referrals = self.db.query(Referral).filter(Referral.referrer_user_id == user_id).all()
        self.db.commit()
        return {
            "plan": wallet.plan,
            "monthly": wallet.monthly_balance,
            "bonus": wallet.bonus_balance,
            "purchased": wallet.purchased_balance,
            "reserved": wallet.reserved_balance,
            "total_available": wallet.monthly_balance + wallet.bonus_balance + wallet.purchased_balance - wallet.reserved_balance,
            "monthly_allowance": settings.credit_pro_monthly if wallet.plan in {"PRO", "STUDENT_PRO"} else settings.credit_free_monthly,
            "renewal_date": wallet.cycle_end,
            "referral": {"code": code.code, "link": f"{settings.frontend_app_url.rstrip('/')}/r/{code.code}", "successful": sum(r.status == "rewarded" for r in referrals), "pending": sum(r.status == "pending" for r in referrals), "credits_earned": sum(settings.credit_referral_reward for r in referrals if r.status == "rewarded")},
            "history": [{"id": item.id, "amount": item.amount, "balance_type": item.balance_type, "type": item.transaction_type, "source": item.source, "created_at": item.created_at} for item in recent],
        }

    def reserve(self, user_id: str, request_id: str, workload: str, estimate: int | None = None) -> CreditReservation:
        existing = self.db.query(CreditReservation).filter_by(user_id=user_id, request_id=request_id).first()
        if existing:
            return existing
        estimate = max(0, int(estimate if estimate is not None else settings.credit_costs.get(workload, settings.credit_costs.get("agent_workflow", 20))))
        wallet = self.wallet(user_id, lock=True)
        available = wallet.monthly_balance + wallet.bonus_balance + wallet.purchased_balance - wallet.reserved_balance
        if estimate > available:
            raise InsufficientCreditsError("insufficient_credits")
        reservation = CreditReservation(user_id=user_id, request_id=request_id, workload=workload, estimated_credits=estimate, expires_at=utc_now() + timedelta(minutes=30))
        wallet.reserved_balance += estimate
        self.db.add(reservation)
        self.db.commit()
        self.db.refresh(reservation)
        return reservation

    def settle(self, user_id: str, request_id: str, actual: int, *, meaningful_output: bool = True) -> CreditReservation:
        reservation = self.db.query(CreditReservation).filter_by(user_id=user_id, request_id=request_id).with_for_update().first()
        if not reservation or reservation.status != "reserved":
            if reservation:
                return reservation
            raise ValueError("Credit reservation not found.")
        wallet = self.wallet(user_id, lock=True)
        charge = min(max(0, int(actual if meaningful_output else 0)), reservation.estimated_credits)
        wallet.reserved_balance = max(0, wallet.reserved_balance - reservation.estimated_credits)
        remaining = charge
        for attr, kind in (("monthly_balance", "MONTHLY"), ("bonus_balance", "BONUS"), ("purchased_balance", "PURCHASED")):
            taken = min(getattr(wallet, attr), remaining)
            if taken:
                setattr(wallet, attr, getattr(wallet, attr) - taken)
                self._ledger(wallet, -taken, kind, "usage", reservation.workload, request_id)
                remaining -= taken
        reservation.settled_credits, reservation.status = charge, "settled"
        self.db.commit()
        return reservation

    def release(self, user_id: str, request_id: str) -> CreditReservation | None:
        reservation = self.db.query(CreditReservation).filter_by(user_id=user_id, request_id=request_id).with_for_update().first()
        if not reservation or reservation.status != "reserved":
            return reservation
        wallet = self.wallet(user_id, lock=True)
        wallet.reserved_balance = max(0, wallet.reserved_balance - reservation.estimated_credits)
        reservation.status = "released"
        self.db.commit()
        return reservation

    def referral_code(self, user_id: str) -> ReferralCode:
        row = self.db.query(ReferralCode).filter_by(user_id=user_id).first()
        if not row:
            row = ReferralCode(user_id=user_id, code=secrets.token_urlsafe(9).replace("-", "").replace("_", "").upper()[:12])
            self.db.add(row)
            self.db.flush()
        return row

    def apply_referral(self, user: User, code: str) -> Referral:
        owner = self.db.query(ReferralCode).filter(ReferralCode.code == code.upper(), ReferralCode.active.is_(True)).first()
        if not owner:
            raise ValueError("Invalid referral code.")
        if owner.user_id == user.id:
            raise ValueError("Self-referrals are not allowed.")
        existing = self.db.query(Referral).filter_by(referred_user_id=user.id).first()
        if existing:
            return existing
        month_start = utc_now().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        rewarded = self.db.query(Referral).filter(Referral.referrer_user_id == owner.user_id, Referral.status == "rewarded", Referral.rewarded_at >= month_start).count()
        if rewarded >= settings.credit_referral_monthly_cap:
            raise ValueError("This referral code reached its monthly reward limit.")
        referral = Referral(referrer_user_id=owner.user_id, referred_user_id=user.id, referral_code=owner.code, status="rewarded", rewarded_at=utc_now())
        self.db.add(referral)
        self.db.flush()
        for uid, source in ((owner.user_id, "referral_reward"), (user.id, "referral_welcome")):
            wallet = self.wallet(uid, lock=True)
            wallet.bonus_balance += settings.credit_referral_reward
            self._ledger(wallet, settings.credit_referral_reward, "REFERRAL_BONUS", "referral", source, referral.id)
        self.db.commit()
        return referral

    def products(self, plan: str | None = None) -> list[CreditProduct]:
        rows = self.db.query(CreditProduct).filter(CreditProduct.active.is_(True)).order_by(CreditProduct.display_order).all()
        return [p for p in rows if not plan or plan.upper() in (p.plan_eligibility or {}).get("plans", ["FREE", "PRO", "STUDENT_PRO"])]

    def create_purchase_order(self, user: User, product_id: str) -> dict[str, Any]:
        product = self.db.query(CreditProduct).filter_by(id=product_id, active=True).first()
        if not product or product not in self.products(self.plan_code(user.id)):
            raise ValueError("Credit product is unavailable.")
        order = RazorpayGateway().create_order(amount=product.amount_inr * 100, currency="INR", receipt=f"credits_{user.id[:8]}_{secrets.token_hex(4)}", notes={"user_id": user.id, "credit_product_id": product.id, "purchase_type": "credits"})
        purchase = CreditPurchase(user_id=user.id, credit_product_id=product.id, razorpay_order_id=str(order["id"]), amount=product.amount_inr * 100, credits=product.credits, status="created")
        self.db.add(purchase)
        self.db.commit()
        return {"purchase_id": purchase.id, "order_id": purchase.razorpay_order_id, "amount": purchase.amount, "currency": "INR", "credits": product.credits, "name": product.name, "key_id": settings.razorpay_key_id}

    def verify_purchase(self, user_id: str, order_id: str, payment_id: str, signature: str) -> CreditPurchase:
        purchase = self.db.query(CreditPurchase).filter_by(user_id=user_id, razorpay_order_id=order_id).with_for_update().first()
        if not purchase:
            raise ValueError("Credit purchase not found.")
        if purchase.status == "completed":
            return purchase
        gateway = RazorpayGateway()
        if not gateway.verify_payment_signature(payment_id=payment_id, order_or_subscription_id=order_id, signature=signature):
            raise BillingProviderError("Payment verification failed.", category="invalid_signature")
        payment = gateway.fetch_payment(payment_id)
        if str(payment.get("status", "")).lower() not in {"captured", "authorized", "paid"} or int(payment.get("amount") or 0) != purchase.amount:
            raise BillingProviderError("Payment has not been captured.", category="invalid_payment")
        self._complete_purchase(purchase, payment_id, payment)
        self.db.commit()
        return purchase

    def apply_payment_webhook(self, payment: dict, event_type: str) -> CreditPurchase | None:
        order_id = str(payment.get("order_id") or "")
        if not order_id:
            return None
        purchase = self.db.query(CreditPurchase).filter_by(razorpay_order_id=order_id).with_for_update().first()
        if not purchase:
            return None
        payment_id = str(payment.get("id") or purchase.razorpay_payment_id or "")
        if event_type in {"payment.captured", "payment.authorized"} and int(payment.get("amount") or 0) == purchase.amount:
            self._complete_purchase(purchase, payment_id, payment)
        elif event_type in {"refund.processed", "payment.refunded"} and purchase.status == "completed":
            wallet = self.wallet(purchase.user_id, lock=True)
            reversal = min(wallet.purchased_balance, purchase.credits)
            wallet.purchased_balance -= reversal
            purchase.status = "refunded"
            self._ledger(wallet, -reversal, "PURCHASED", "reversal", "razorpay_refund", f"refund:{payment_id}", payment_id)
        return purchase

    def _complete_purchase(self, purchase: CreditPurchase, payment_id: str, metadata: dict) -> None:
        if purchase.status == "completed":
            return
        wallet = self.wallet(purchase.user_id, lock=True)
        wallet.purchased_balance += purchase.credits
        purchase.razorpay_payment_id, purchase.status, purchase.completed_at, purchase.extra_metadata = payment_id, "completed", utc_now(), metadata
        self._ledger(wallet, purchase.credits, "PURCHASED", "purchase", "razorpay", purchase.razorpay_order_id, payment_id)

    def _ledger(self, wallet: CreditWallet, amount: int, balance_type: str, transaction_type: str, source: str, request_id: str | None, external: str | None = None) -> None:
        exists = self.db.query(CreditLedger).filter_by(user_id=wallet.user_id, request_id=request_id, transaction_type=transaction_type).first() if request_id else None
        if not exists:
            self.db.add(CreditLedger(user_id=wallet.user_id, amount=amount, balance_type=balance_type, transaction_type=transaction_type, source=source, request_id=request_id, external_reference=external))
