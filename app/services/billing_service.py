from __future__ import annotations

import hashlib
import hmac
import json
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx
import razorpay
from sqlalchemy.orm import Session

from app.core.config.settings import settings
from app.models.commercial import BillingEvent, BillingInvoice, BillingPayment, Plan, PlanEntitlement, Subscription
from app.models.mixins import utc_now
from app.models.user import User
from app.services.commercial_service import PlanService, StudentVerificationService, SubscriptionService, UsageService


logger = logging.getLogger(__name__)


class BillingConfigurationError(ValueError):
    pass


class BillingProviderError(RuntimeError):
    def __init__(self, message: str, *, category: str = "provider_error", retryable: bool = False):
        super().__init__(message)
        self.category = category
        self.retryable = retryable


@dataclass
class FeatureAccessSnapshot:
    can_use_voice: bool
    can_upload_files: bool
    can_use_research: bool
    can_create_projects: bool
    max_storage_mb: int
    max_messages: int
    max_team_members: int


class FeatureAccessService:
    def __init__(self, db: Session):
        self.db = db
        self.subscription_service = SubscriptionService(db)
        self.plan_service = PlanService(db)

    def snapshot(self, user_id: str) -> FeatureAccessSnapshot:
        subscription = self.subscription_service.active_subscription(user_id)
        entitlements = {
            item.entitlement_key: item.limit_value
            for item in self.plan_service.entitlements(subscription.plan_id)
        }
        return FeatureAccessSnapshot(
            can_use_voice=entitlements.get("voice_minutes", 0) > 0,
            can_upload_files=entitlements.get("file_uploads", 0) > 0,
            can_use_research=entitlements.get("research_runs", 0) > 0,
            can_create_projects=entitlements.get("active_projects", 0) > 0,
            max_storage_mb=entitlements.get("max_file_size_mb", 0),
            max_messages=entitlements.get("chat_ai_units", 0),
            max_team_members=1,
        )


class RazorpayGateway:
    def __init__(self) -> None:
        if not settings.razorpay_key_id or not settings.razorpay_key_secret:
            raise BillingConfigurationError("Razorpay is not configured yet.")
        self.base_url = settings.razorpay_api_base_url.rstrip("/")
        self.client = razorpay.Client(auth=(settings.razorpay_key_id, settings.razorpay_key_secret))

    def create_customer(self, *, name: str, email: str, contact: str | None = None, notes: dict[str, str] | None = None) -> dict[str, Any]:
        payload: dict[str, Any] = {"name": name, "email": email}
        if contact:
            payload["contact"] = contact
        if notes:
            payload["notes"] = notes
        return self._request("POST", "/customers", json_body=payload)

    def create_subscription(self, *, plan_id: str, customer_id: str, total_count: int, notes: dict[str, str]) -> dict[str, Any]:
        return self._request(
            "POST",
            "/subscriptions",
            json_body={
                "plan_id": plan_id,
                "customer_notify": 0,
                "total_count": total_count,
                "quantity": 1,
                "customer_id": customer_id,
                "notes": notes,
            },
        )

    def create_order(self, *, amount: int, currency: str, receipt: str, notes: dict[str, str] | None = None) -> dict[str, Any]:
        if amount < 100:
            raise BillingProviderError("Amount must be at least 100 paise.", category="invalid_request")
        try:
            return self.client.order.create(
                {
                    "amount": amount,
                    "currency": currency,
                    "receipt": receipt,
                    "payment_capture": 1,
                    "notes": notes or {},
                }
            )
        except razorpay.errors.BadRequestError as exc:
            raise BillingProviderError("Could not create the order.", category="invalid_request") from exc
        except razorpay.errors.ServerError as exc:
            raise BillingProviderError("Billing provider is temporarily unavailable.", category="provider_error", retryable=True) from exc
        except razorpay.errors.GatewayError as exc:
            raise BillingProviderError("Billing provider is temporarily unavailable.", category="provider_error", retryable=True) from exc
        except razorpay.errors.SignatureVerificationError as exc:
            raise BillingProviderError("Billing request could not be verified.", category="authentication") from exc
        except Exception as exc:
            raise BillingProviderError("Could not create the order.", category="provider_error", retryable=True) from exc

    def fetch_subscription(self, provider_subscription_id: str) -> dict[str, Any]:
        return self._request("GET", f"/subscriptions/{provider_subscription_id}")

    def fetch_payment(self, provider_payment_id: str) -> dict[str, Any]:
        return self._request("GET", f"/payments/{provider_payment_id}")

    def cancel_subscription(self, provider_subscription_id: str, *, cancel_at_cycle_end: bool = True) -> dict[str, Any]:
        return self._request(
            "POST",
            f"/subscriptions/{provider_subscription_id}/cancel",
            json_body={"cancel_at_cycle_end": 1 if cancel_at_cycle_end else 0},
        )

    def resume_subscription(self, provider_subscription_id: str) -> dict[str, Any]:
        return self._request("POST", f"/subscriptions/{provider_subscription_id}/resume", json_body={"resume_at": "now"})

    def verify_payment_signature(self, *, payment_id: str, order_or_subscription_id: str, signature: str) -> bool:
        payload = f"{order_or_subscription_id}|{payment_id}".encode("utf-8")
        expected = hmac.new(settings.razorpay_key_secret.encode("utf-8"), payload, hashlib.sha256).hexdigest()
        return hmac.compare_digest(expected, signature)

    def verify_webhook_signature(self, *, raw_body: bytes, signature: str | None) -> bool:
        if not settings.razorpay_webhook_secret or not signature:
            return False
        expected = hmac.new(settings.razorpay_webhook_secret.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()
        return hmac.compare_digest(expected, signature)

    def _request(self, method: str, path: str, json_body: dict[str, Any] | None = None) -> dict[str, Any]:
        url = f"{self.base_url}{path}"
        try:
            with httpx.Client(timeout=20.0, auth=(settings.razorpay_key_id, settings.razorpay_key_secret)) as client:
                response = client.request(method, url, json=json_body)
                if response.status_code >= 400:
                    detail = self._safe_error(response)
                    raise BillingProviderError(detail, category=self._status_category(response.status_code), retryable=response.status_code >= 500)
                return response.json() if response.content else {}
        except httpx.TimeoutException as exc:
            raise BillingProviderError("Billing provider timed out.", category="timeout", retryable=True) from exc
        except httpx.HTTPError as exc:
            raise BillingProviderError("Billing provider is unavailable.", category="network", retryable=True) from exc

    def _safe_error(self, response: httpx.Response) -> str:
        try:
            data = response.json()
            error = data.get("error") or {}
            if isinstance(error, dict):
                return str(error.get("description") or error.get("reason") or error.get("code") or "Billing request failed.")
        except Exception:
            pass
        return "Billing request failed."

    def _status_category(self, status_code: int) -> str:
        if status_code == 401:
            return "authentication"
        if status_code == 429:
            return "rate_limit"
        if 400 <= status_code < 500:
            return "invalid_request"
        return "provider_error"


class RazorpayBillingService:
    def __init__(self, db: Session):
        self.db = db
        self.plan_service = PlanService(db)
        self.subscription_service = SubscriptionService(db)
        self.usage_service = UsageService(db)
        self.student_service = StudentVerificationService(db)
        self.gateway = RazorpayGateway()

    def create_subscription(self, user: User, *, plan_code: str, billing_interval: str) -> dict[str, Any]:
        plan = self.plan_service.get_by_code(plan_code)
        if plan.code == "FREE":
            raise ValueError("Free plan does not require checkout.")
        if plan.code == "STUDENT_PRO" and not self.student_service.is_student_pricing_available(user.id):
            raise ValueError("Verify student status before selecting Student Pro.")
        provider_plan_id = self._provider_plan_id(plan.code, billing_interval)
        profile_name = getattr(getattr(user, "profile", None), "display_name", None)
        customer_id = self._existing_provider_customer_id(user.id)
        if not customer_id:
            customer = self.gateway.create_customer(
                name=profile_name or user.email.split("@", 1)[0],
                email=user.email,
                notes={"user_id": user.id, "plan_code": plan.code},
            )
            customer_id = str(customer.get("id"))
        remote_subscription = self.gateway.create_subscription(
            plan_id=provider_plan_id,
            customer_id=customer_id,
            total_count=12 if billing_interval == "monthly" else 1,
            notes={"user_id": user.id, "plan_code": plan.code, "billing_interval": billing_interval},
        )
        local = Subscription(
            user_id=user.id,
            plan_id=plan.id,
            provider="razorpay",
            provider_plan_id=provider_plan_id,
            provider_customer_id=customer_id,
            provider_subscription_id=str(remote_subscription.get("id")),
            status=str(remote_subscription.get("status") or "created"),
            billing_interval=billing_interval,
            currency=plan.currency,
            current_period_start=_unix_to_dt(remote_subscription.get("current_start")),
            current_period_end=_unix_to_dt(remote_subscription.get("current_end")),
            next_renewal_at=_unix_to_dt(remote_subscription.get("charge_at")),
            extra_metadata={"provider_payload": remote_subscription},
        )
        self.db.add(local)
        self.db.commit()
        self.db.refresh(local)
        return {
            "provider": "razorpay",
            "key_id": settings.razorpay_key_id,
            "subscription_id": local.provider_subscription_id,
            "customer_id": local.provider_customer_id,
            "plan_code": plan.code,
            "billing_interval": billing_interval,
            "amount": plan.annual_price if billing_interval == "annual" else plan.monthly_price,
            "currency": plan.currency,
            "name": settings.razorpay_checkout_name,
            "description": plan.description,
            "prefill_email": user.email,
            "prefill_name": profile_name or user.email.split("@", 1)[0],
            "theme_color": settings.razorpay_checkout_theme_color,
        }

    def _existing_provider_customer_id(self, user_id: str) -> str | None:
        subscription = (
            self.db.query(Subscription)
            .filter(
                Subscription.user_id == user_id,
                Subscription.provider == "razorpay",
                Subscription.provider_customer_id.isnot(None),
            )
            .order_by(Subscription.created_at.desc())
            .first()
        )
        if not subscription or not subscription.provider_customer_id:
            return None
        return str(subscription.provider_customer_id)

    def create_order(self, user: User, *, amount: int, currency: str, receipt: str | None, plan_code: str | None, billing_interval: str) -> dict[str, Any]:
        plan = self.plan_service.get_by_code(plan_code) if plan_code else None
        if plan:
            expected_amount = plan.annual_price if billing_interval == "annual" else plan.monthly_price
            if plan.code == "FREE":
                raise ValueError("Free plan does not require payment.")
            if plan.code == "STUDENT_PRO" and not self.student_service.is_student_pricing_available(user.id):
                raise ValueError("Verify student status before choosing Student Pro.")
            amount = expected_amount
            currency = plan.currency
        if amount < 100:
            raise ValueError("Minimum amount is 100 paise.")
        resolved_receipt = receipt or f"ceaser_{user.id[:8]}_{int(utc_now().timestamp())}"
        order = self.gateway.create_order(
            amount=amount,
            currency=currency,
            receipt=resolved_receipt,
            notes={
                "user_id": user.id,
                "plan_code": plan.code if plan else "",
                "billing_interval": billing_interval,
            },
        )
        profile_name = getattr(getattr(user, "profile", None), "display_name", None)
        return {
            "order_id": str(order.get("id")),
            "amount": int(order.get("amount") or amount),
            "currency": str(order.get("currency") or currency),
            "key_id": settings.razorpay_key_id,
            "receipt": str(order.get("receipt") or resolved_receipt),
            "plan_code": plan.code if plan else plan_code,
            "billing_interval": billing_interval,
            "name": settings.razorpay_checkout_name,
            "description": plan.description if plan else "CEASER plan upgrade",
            "prefill_email": user.email,
            "prefill_name": profile_name or user.email.split("@", 1)[0],
            "theme_color": settings.razorpay_checkout_theme_color,
        }

    def verify_payment(
        self,
        user: User,
        *,
        payment_id: str,
        order_id: str | None,
        subscription_id: str | None,
        signature: str,
        plan_code: str | None = None,
        billing_interval: str = "monthly",
    ) -> Subscription:
        identifier = order_id or subscription_id
        if not identifier:
            raise ValueError("Order id or subscription id is required.")
        if not self.gateway.verify_payment_signature(payment_id=payment_id, order_or_subscription_id=identifier, signature=signature):
            raise BillingProviderError("Payment verification failed.", category="invalid_signature")
        payment = self.gateway.fetch_payment(payment_id)
        if subscription_id:
            remote_subscription = self.gateway.fetch_subscription(subscription_id)
            subscription = (
                self.db.query(Subscription)
                .filter(Subscription.user_id == user.id, Subscription.provider_subscription_id == subscription_id)
                .order_by(Subscription.created_at.desc())
                .first()
            )
            if not subscription:
                raise ValueError("Subscription record not found.")
            subscription.provider_payment_id = payment_id
            subscription.provider_invoice_id = payment.get("invoice_id")
            self._apply_subscription_payload(subscription, remote_subscription)
            self._upsert_payment(user_id=user.id, subscription=subscription, payment=payment)
            self.db.commit()
            self.db.refresh(subscription)
            return subscription

        resolved_plan_code = str(payment.get("notes", {}).get("plan_code") or plan_code or "PRO").upper()
        resolved_interval = str(payment.get("notes", {}).get("billing_interval") or billing_interval or "monthly").lower()
        plan = self.plan_service.get_by_code(resolved_plan_code)
        subscription = self._upsert_order_subscription(
            user=user,
            plan=plan,
            billing_interval=resolved_interval,
            order_id=identifier,
            payment=payment,
        )
        self._upsert_payment(user_id=user.id, subscription=subscription, payment=payment)
        self.db.commit()
        self.db.refresh(subscription)
        return subscription

    def overview(self, user_id: str) -> dict[str, Any]:
        subscription = self._overview_subscription(user_id)
        plan = self.db.query(Plan).filter(Plan.id == subscription.plan_id).first() or self.plan_service.get_by_code("FREE")
        payments = (
            self.db.query(BillingPayment)
            .filter(BillingPayment.user_id == user_id)
            .order_by(BillingPayment.created_at.desc())
            .limit(10)
            .all()
        )
        invoices = (
            self.db.query(BillingInvoice)
            .filter(BillingInvoice.user_id == user_id)
            .order_by(BillingInvoice.created_at.desc())
            .limit(10)
            .all()
        )
        return {
            "plan": plan,
            "subscription": subscription,
            "entitlements": self.plan_service.entitlements(subscription.plan_id),
            "usage": self.usage_service.summary(user_id),
            "payments": payments,
            "invoices": invoices,
            "student_pricing_available": self.student_service.is_student_pricing_available(user_id),
        }

    def _overview_subscription(self, user_id: str) -> Subscription:
        now = utc_now()
        active_rows = (
            self.db.query(Subscription)
            .filter(
                Subscription.user_id == user_id,
                Subscription.status.in_(["active", "grace_period", "authenticated"]),
            )
            .order_by(Subscription.created_at.desc())
            .all()
        )

        for subscription in active_rows:
            if not self._subscription_current_for_billing(subscription, now):
                continue
            if subscription.provider == "razorpay" and subscription.provider_subscription_id:
                return subscription

        for subscription in active_rows:
            if not self._subscription_current_for_billing(subscription, now):
                continue
            if subscription.provider in {"system", "test"}:
                return subscription

        return self._free_subscription(user_id)

    def _subscription_current_for_billing(self, subscription: Subscription, now: datetime) -> bool:
        if subscription.current_period_end and subscription.current_period_end < now:
            return False
        return True

    def _free_subscription(self, user_id: str) -> Subscription:
        free = self.plan_service.get_by_code("FREE")
        subscription = (
            self.db.query(Subscription)
            .filter(
                Subscription.user_id == user_id,
                Subscription.plan_id == free.id,
                Subscription.provider == "system",
                Subscription.status.in_(["active", "grace_period"]),
            )
            .order_by(Subscription.created_at.desc())
            .first()
        )
        if subscription:
            return subscription

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

    def invoices(self, user_id: str) -> list[BillingInvoice]:
        return (
            self.db.query(BillingInvoice)
            .filter(BillingInvoice.user_id == user_id)
            .order_by(BillingInvoice.created_at.desc())
            .all()
        )

    def cancel(self, user_id: str) -> Subscription:
        subscription = self._provider_subscription(user_id)
        remote = self.gateway.cancel_subscription(subscription.provider_subscription_id, cancel_at_cycle_end=True)
        self._apply_subscription_payload(subscription, remote)
        subscription.cancel_at_period_end = True
        self.db.commit()
        self.db.refresh(subscription)
        return subscription

    def resume(self, user_id: str) -> Subscription:
        subscription = self._provider_subscription(user_id)
        remote = self.gateway.resume_subscription(subscription.provider_subscription_id)
        self._apply_subscription_payload(subscription, remote)
        subscription.cancel_at_period_end = False
        subscription.cancelled_at = None
        self.db.commit()
        self.db.refresh(subscription)
        return subscription

    def process_webhook(self, raw_body: bytes, signature: str | None) -> BillingEvent:
        if not self.gateway.verify_webhook_signature(raw_body=raw_body, signature=signature):
            raise BillingProviderError("Webhook verification failed.", category="invalid_signature")
        payload = json.loads(raw_body.decode("utf-8"))
        event_type = str(payload.get("event") or "unknown")
        provider_event_id = self._provider_event_id(payload, event_type)
        payload_hash = hashlib.sha256(raw_body).hexdigest()
        existing = self.db.query(BillingEvent).filter(BillingEvent.provider == "razorpay", BillingEvent.provider_event_id == provider_event_id).first()
        if existing:
            return existing
        event = BillingEvent(
            provider="razorpay",
            provider_event_id=provider_event_id,
            event_type=event_type,
            signature_verified=True,
            payload_hash=payload_hash,
            processing_status="processing",
        )
        self.db.add(event)
        self.db.flush()
        self._apply_webhook_payload(payload)
        event.processing_status = "processed"
        event.processed_at = utc_now()
        self.db.commit()
        self.db.refresh(event)
        return event

    def _apply_webhook_payload(self, payload: dict[str, Any]) -> None:
        event_type = str(payload.get("event") or "")
        entity = self._payload_entity(payload)
        subscription_id = entity.get("subscription_id") or entity.get("id") if "subscription" in event_type else entity.get("subscription_id")
        if subscription_id:
            subscription = self.db.query(Subscription).filter(Subscription.provider_subscription_id == str(subscription_id)).order_by(Subscription.created_at.desc()).first()
            if subscription:
                if "subscription" in event_type and entity.get("id") == subscription.provider_subscription_id:
                    self._apply_subscription_payload(subscription, entity)
                elif "payment" in event_type:
                    subscription.provider_payment_id = entity.get("id") or subscription.provider_payment_id
                    if entity.get("invoice_id"):
                        subscription.provider_invoice_id = entity.get("invoice_id")
                elif "invoice" in event_type:
                    subscription.provider_invoice_id = entity.get("id") or subscription.provider_invoice_id
        if event_type.startswith("payment.") and entity.get("id"):
            self._upsert_payment_by_event(entity)
        if event_type.startswith("invoice.") and entity.get("id"):
            self._upsert_invoice_by_event(entity)
        if event_type in {"payment.captured", "payment.authorized", "payment.refunded", "refund.processed"}:
            from app.services.credit_service import CreditService
            CreditService(self.db).apply_payment_webhook(entity, event_type)

    def _upsert_payment(self, *, user_id: str, subscription: Subscription, payment: dict[str, Any]) -> BillingPayment:
        record = self.db.query(BillingPayment).filter(BillingPayment.provider == "razorpay", BillingPayment.provider_payment_id == str(payment.get("id"))).first()
        if not record:
            record = BillingPayment(
                user_id=user_id,
                subscription_id=subscription.id,
                plan_id=subscription.plan_id,
                provider="razorpay",
                provider_payment_id=str(payment.get("id")),
            )
            self.db.add(record)
        record.provider_invoice_id = payment.get("invoice_id")
        record.amount = int(payment.get("amount") or 0)
        record.currency = str(payment.get("currency") or subscription.currency or "INR")
        record.status = str(payment.get("status") or "captured")
        record.method = payment.get("method")
        record.captured_at = _unix_to_dt(payment.get("captured_at"))
        record.extra_metadata = payment
        return record

    def _upsert_payment_by_event(self, payment: dict[str, Any]) -> None:
        provider_subscription_id = payment.get("subscription_id")
        subscription = None
        if provider_subscription_id:
            subscription = self.db.query(Subscription).filter(Subscription.provider_subscription_id == str(provider_subscription_id)).order_by(Subscription.created_at.desc()).first()
        if not subscription:
            return
        self._upsert_payment(user_id=subscription.user_id, subscription=subscription, payment=payment)

    def _upsert_invoice_by_event(self, invoice: dict[str, Any]) -> None:
        provider_subscription_id = invoice.get("subscription_id")
        subscription = None
        if provider_subscription_id:
            subscription = self.db.query(Subscription).filter(Subscription.provider_subscription_id == str(provider_subscription_id)).order_by(Subscription.created_at.desc()).first()
        if not subscription:
            return
        record = self.db.query(BillingInvoice).filter(BillingInvoice.provider == "razorpay", BillingInvoice.provider_invoice_id == str(invoice.get("id"))).first()
        if not record:
            record = BillingInvoice(
                user_id=subscription.user_id,
                subscription_id=subscription.id,
                plan_id=subscription.plan_id,
                provider="razorpay",
                provider_invoice_id=str(invoice.get("id")),
            )
            self.db.add(record)
        record.invoice_number = invoice.get("invoice_number")
        record.amount = int(invoice.get("amount") or 0)
        record.currency = str(invoice.get("currency") or subscription.currency or "INR")
        record.status = str(invoice.get("status") or "issued")
        record.hosted_url = invoice.get("short_url") or invoice.get("hosted_url")
        record.issued_at = _unix_to_dt(invoice.get("issued_at"))
        record.due_at = _unix_to_dt(invoice.get("expire_by") or invoice.get("due_at"))
        record.paid_at = _unix_to_dt(invoice.get("paid_at"))
        record.extra_metadata = invoice

    def _provider_subscription(self, user_id: str) -> Subscription:
        subscription = (
            self.db.query(Subscription)
            .filter(Subscription.user_id == user_id, Subscription.provider == "razorpay", Subscription.provider_subscription_id.isnot(None))
            .order_by(Subscription.created_at.desc())
            .first()
        )
        if not subscription:
            raise ValueError("No Razorpay subscription found for this account.")
        return subscription

    def _upsert_order_subscription(
        self,
        *,
        user: User,
        plan: Plan,
        billing_interval: str,
        order_id: str,
        payment: dict[str, Any],
    ) -> Subscription:
        subscription = (
            self.db.query(Subscription)
            .filter(Subscription.user_id == user.id, Subscription.provider == "razorpay", Subscription.provider_payment_id == str(payment.get("id")))
            .order_by(Subscription.created_at.desc())
            .first()
        )
        if not subscription:
            subscription = Subscription(user_id=user.id, plan_id=plan.id, provider="razorpay")
            self.db.add(subscription)
        now = utc_now()
        end = now + (timedelta(days=365) if billing_interval == "annual" else timedelta(days=30))
        subscription.plan_id = plan.id
        subscription.provider_plan_id = plan.code
        subscription.provider_payment_id = str(payment.get("id"))
        subscription.provider_invoice_id = payment.get("invoice_id")
        subscription.provider_subscription_id = None
        subscription.status = "active" if str(payment.get("status") or "").lower() in {"captured", "authorized", "paid"} else str(payment.get("status") or "active")
        subscription.billing_interval = billing_interval
        subscription.currency = str(payment.get("currency") or plan.currency or "INR")
        subscription.current_period_start = now
        subscription.current_period_end = end
        subscription.next_renewal_at = end
        subscription.cancel_at_period_end = False
        subscription.extra_metadata = {
            "order_id": order_id,
            "payment_payload": payment,
        }
        return subscription

    def _provider_plan_id(self, plan_code: str, billing_interval: str) -> str:
        plan_id = settings.razorpay_plan_map.get(plan_code.upper(), {}).get(billing_interval.lower())
        if not plan_id:
            raise BillingConfigurationError(f"Razorpay plan mapping is missing for {plan_code} ({billing_interval}).")
        return plan_id

    def _apply_subscription_payload(self, subscription: Subscription, payload: dict[str, Any]) -> None:
        subscription.status = str(payload.get("status") or subscription.status)
        subscription.provider_plan_id = payload.get("plan_id") or subscription.provider_plan_id
        subscription.provider_customer_id = payload.get("customer_id") or subscription.provider_customer_id
        subscription.current_period_start = _unix_to_dt(payload.get("current_start")) or subscription.current_period_start
        subscription.current_period_end = _unix_to_dt(payload.get("current_end")) or subscription.current_period_end
        subscription.next_renewal_at = _unix_to_dt(payload.get("charge_at")) or subscription.next_renewal_at
        subscription.cancel_at_period_end = bool(payload.get("has_scheduled_changes") or subscription.cancel_at_period_end)
        if subscription.status == "cancelled":
            subscription.cancelled_at = utc_now()
        if subscription.status == "paused":
            subscription.paused_at = utc_now()
        subscription.extra_metadata = payload

    def _provider_event_id(self, payload: dict[str, Any], event_type: str) -> str:
        entity = self._payload_entity(payload)
        entity_id = entity.get("id") or entity.get("payment_id") or entity.get("subscription_id")
        if entity_id:
            return f"{event_type}:{entity_id}"
        return f"{event_type}:{hashlib.sha256(json.dumps(payload, sort_keys=True).encode('utf-8')).hexdigest()}"

    def _payload_entity(self, payload: dict[str, Any]) -> dict[str, Any]:
        raw = payload.get("payload") or {}
        for key in ("subscription", "payment", "invoice"):
            item = raw.get(key)
            if isinstance(item, dict) and isinstance(item.get("entity"), dict):
                return item["entity"]
        return {}


def _unix_to_dt(value: Any) -> datetime | None:
    if value in (None, "", 0):
        return None
    try:
        return datetime.fromtimestamp(int(value), tz=timezone.utc)
    except Exception:
        return None
