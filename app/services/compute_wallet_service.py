from __future__ import annotations

from calendar import monthrange
from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Mapping

from sqlalchemy import update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.commercial import ComputeWallet, ComputeWalletTransaction, UsageLedger
from app.models.mixins import utc_now

_PRECISION = Decimal("0.000000001")
_SENSITIVE = ("token", "secret", "password", "credential", "api_key", "authorization")


def _decimal(value: Any) -> Decimal:
    return Decimal(str(value)).quantize(_PRECISION, rounding=ROUND_HALF_UP)


def _safe_metadata(metadata: Mapping[str, Any] | None) -> dict[str, Any]:
    return {
        key: value for key, value in (metadata or {}).items()
        if not any(part in key.lower() for part in _SENSITIVE)
        and (isinstance(value, (str, int, float, bool)) or value is None)
    }


def _monthly_period(at: datetime) -> tuple[datetime, datetime]:
    start = at.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    end = at.replace(day=monthrange(at.year, at.month)[1], hour=23, minute=59, second=59, microsecond=999999)
    return start, end


class ComputeWalletService:
    """Shadow CU accounting only. It never authorizes or rejects a request."""

    def __init__(self, db: Session):
        self.db = db

    def wallet(
        self, user_id: str, *, at: datetime | None = None, plan_key: str | None = None,
        included_cu: Any | None = None, lock: bool = False,
    ) -> ComputeWallet:
        period_start, period_end = _monthly_period(at or utc_now())
        query = self.db.query(ComputeWallet).filter_by(user_id=user_id, period_start=period_start, period_end=period_end)
        wallet = query.with_for_update().first() if lock else query.first()
        if wallet is None:
            wallet = ComputeWallet(
                user_id=user_id, plan_key=plan_key, period_start=period_start, period_end=period_end,
                included_cu=_decimal(included_cu) if included_cu is not None else None,
                bonus_cu=Decimal("0"), used_cu=Decimal("0"), reserved_cu=Decimal("0"),
            )
            try:
                with self.db.begin_nested():
                    self.db.add(wallet)
                    self.db.flush()
            except IntegrityError:
                wallet = query.with_for_update().one() if lock else query.one()
        return wallet

    def _existing(self, key: str) -> ComputeWalletTransaction | None:
        return self.db.query(ComputeWalletTransaction).filter_by(idempotency_key=key).first()

    def _transaction(
        self, wallet: ComputeWallet, *, transaction_type: str, amount: Any, source: str,
        idempotency_key: str, request_id: str | None = None, reference_id: str | None = None,
        metadata: Mapping[str, Any] | None = None,
    ) -> ComputeWalletTransaction:
        existing = self._existing(idempotency_key)
        if existing:
            return existing
        row = ComputeWalletTransaction(
            wallet_id=wallet.id, user_id=wallet.user_id, request_id=request_id,
            transaction_type=transaction_type, amount_cu=_decimal(amount), source=source,
            reference_id=reference_id, idempotency_key=idempotency_key,
            extra_metadata=_safe_metadata(metadata),
        )
        self.db.add(row)
        self.db.flush()
        return row

    def record_usage(self, event: UsageLedger) -> ComputeWalletTransaction | None:
        if event.compute_unit_status not in {"calculated", "free"} or event.compute_units is None:
            return None
        amount = _decimal(event.compute_units)
        if amount == 0:
            return None
        key = f"usage:{event.id}"
        existing = self._existing(key)
        if existing:
            return existing
        wallet = self.wallet(event.user_id, at=event.created_at, lock=True)
        existing = self._existing(key)
        if existing:
            return existing
        result = self.db.execute(
            update(ComputeWallet).where(ComputeWallet.id == wallet.id).values(
                used_cu=ComputeWallet.used_cu + amount, updated_at=utc_now(),
            )
        )
        if result.rowcount != 1:
            raise RuntimeError("compute_wallet_update_failed")
        return self._transaction(
            wallet, transaction_type="debit", amount=amount, source="usage_ledger",
            idempotency_key=key, request_id=event.request_id, reference_id=event.id,
        )

    def reserve(self, user_id: str, request_id: str, amount: Any, *, source: str = "estimate") -> ComputeWalletTransaction | None:
        amount_cu = _decimal(amount)
        if amount_cu <= 0:
            return None
        key = f"reserve:{user_id}:{request_id}"
        existing = self._existing(key)
        if existing:
            return existing
        wallet = self.wallet(user_id, lock=True)
        existing = self._existing(key)
        if existing:
            return existing
        self.db.execute(update(ComputeWallet).where(ComputeWallet.id == wallet.id).values(
            reserved_cu=ComputeWallet.reserved_cu + amount_cu, updated_at=utc_now(),
        ))
        return self._transaction(wallet, transaction_type="reserve", amount=amount_cu, source=source, idempotency_key=key, request_id=request_id)

    def settle(self, user_id: str, request_id: str, actual: Any, *, source: str = "actual_usage") -> ComputeWalletTransaction | None:
        amount_cu = _decimal(actual)
        if amount_cu < 0:
            raise ValueError("actual compute units cannot be negative")
        key = f"settle:{user_id}:{request_id}"
        existing = self._existing(key)
        if existing:
            return existing
        released = self._existing(f"release:{user_id}:{request_id}")
        if released:
            return released
        reserve = self._existing(f"reserve:{user_id}:{request_id}")
        wallet = self.wallet(user_id, lock=True)
        existing = self._existing(key)
        if existing:
            return existing
        reserved = _decimal(reserve.amount_cu) if reserve else Decimal("0")
        self.db.execute(update(ComputeWallet).where(ComputeWallet.id == wallet.id).values(
            reserved_cu=ComputeWallet.reserved_cu - reserved,
            used_cu=ComputeWallet.used_cu + amount_cu,
            updated_at=utc_now(),
        ))
        if reserved > amount_cu:
            self._transaction(
                wallet, transaction_type="release", amount=reserved - amount_cu,
                source="settlement_remainder", idempotency_key=f"settle-release:{user_id}:{request_id}", request_id=request_id,
            )
        return self._transaction(wallet, transaction_type="settle", amount=amount_cu, source=source, idempotency_key=key, request_id=request_id)

    def release(self, user_id: str, request_id: str, *, source: str = "cancelled") -> ComputeWalletTransaction | None:
        key = f"release:{user_id}:{request_id}"
        existing = self._existing(key)
        if existing:
            return existing
        settled = self._existing(f"settle:{user_id}:{request_id}")
        if settled:
            return settled
        reserve = self._existing(f"reserve:{user_id}:{request_id}")
        if not reserve:
            return None
        amount = _decimal(reserve.amount_cu)
        wallet = self.wallet(user_id, lock=True)
        existing = self._existing(key)
        if existing:
            return existing
        self.db.execute(update(ComputeWallet).where(ComputeWallet.id == wallet.id).values(
            reserved_cu=ComputeWallet.reserved_cu - amount, updated_at=utc_now(),
        ))
        return self._transaction(wallet, transaction_type="release", amount=amount, source=source, idempotency_key=key, request_id=request_id)

    def credit(
        self, user_id: str, amount: Any, *, source: str, reference_id: str,
        transaction_type: str = "bonus", metadata: Mapping[str, Any] | None = None,
    ) -> ComputeWalletTransaction | None:
        amount_cu = _decimal(amount)
        if amount_cu <= 0:
            return None
        key = f"{transaction_type}:{user_id}:{source}:{reference_id}"
        existing = self._existing(key)
        if existing:
            return existing
        wallet = self.wallet(user_id, lock=True)
        existing = self._existing(key)
        if existing:
            return existing
        self.db.execute(update(ComputeWallet).where(ComputeWallet.id == wallet.id).values(
            bonus_cu=ComputeWallet.bonus_cu + amount_cu, updated_at=utc_now(),
        ))
        return self._transaction(
            wallet, transaction_type=transaction_type, amount=amount_cu, source=source,
            reference_id=reference_id, idempotency_key=key, metadata=metadata,
        )
