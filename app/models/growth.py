from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, JSON, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database.base import Base
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin, utc_now


class CreditWallet(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "credit_wallets"
    __table_args__ = (UniqueConstraint("user_id", name="uq_credit_wallet_user"),)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    plan: Mapped[str] = mapped_column(String(40), default="FREE", nullable=False)
    monthly_balance: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    bonus_balance: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    purchased_balance: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    reserved_balance: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    cycle_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    cycle_end: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False)


class CreditLedger(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "credit_ledger"
    __table_args__ = (UniqueConstraint("user_id", "request_id", "transaction_type", name="uq_credit_ledger_request_type"),)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    amount: Mapped[int] = mapped_column(Integer, nullable=False)
    balance_type: Mapped[str] = mapped_column(String(30), nullable=False)
    transaction_type: Mapped[str] = mapped_column(String(40), index=True, nullable=False)
    source: Mapped[str] = mapped_column(String(80), nullable=False)
    request_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    external_reference: Mapped[str | None] = mapped_column(String(255), nullable=True)
    extra_metadata: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)


class CreditReservation(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "credit_reservations"
    __table_args__ = (UniqueConstraint("user_id", "request_id", name="uq_credit_reservation_request"),)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    request_id: Mapped[str] = mapped_column(String(120), nullable=False)
    workload: Mapped[str] = mapped_column(String(80), nullable=False)
    estimated_credits: Mapped[int] = mapped_column(Integer, nullable=False)
    settled_credits: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    status: Mapped[str] = mapped_column(String(30), default="reserved", nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class ReferralCode(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "referral_codes"
    __table_args__ = (UniqueConstraint("user_id", name="uq_referral_code_user"), UniqueConstraint("code", name="uq_referral_code"))
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    code: Mapped[str] = mapped_column(String(40), index=True, nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class Referral(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "referrals"
    __table_args__ = (UniqueConstraint("referred_user_id", name="uq_referral_referred_user"),)
    referrer_user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    referred_user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    referral_code: Mapped[str] = mapped_column(String(40), nullable=False)
    status: Mapped[str] = mapped_column(String(30), default="pending", nullable=False)
    rewarded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    suspicious: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)


class CreditProduct(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "credit_products"
    code: Mapped[str] = mapped_column(String(50), unique=True, index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    credits: Mapped[int] = mapped_column(Integer, nullable=False)
    amount_inr: Mapped[int] = mapped_column(Integer, nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    plan_eligibility: Mapped[dict] = mapped_column(JSON, default=lambda: {"plans": ["FREE", "PRO"]}, nullable=False)
    display_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)


class CreditPurchase(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "credit_purchases"
    __table_args__ = (
        UniqueConstraint("razorpay_order_id", name="uq_credit_purchase_order"),
        UniqueConstraint("razorpay_payment_id", name="uq_credit_purchase_payment"),
    )
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    credit_product_id: Mapped[str] = mapped_column(ForeignKey("credit_products.id"), nullable=False)
    razorpay_order_id: Mapped[str] = mapped_column(String(255), nullable=False)
    razorpay_payment_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    amount: Mapped[int] = mapped_column(Integer, nullable=False)
    credits: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(30), default="created", nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    extra_metadata: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
