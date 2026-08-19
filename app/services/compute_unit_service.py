from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Mapping

from sqlalchemy.orm import Session

from app.models.commercial import ComputeUnitPolicy, UsageLedger
from app.models.mixins import utc_now

logger = logging.getLogger(__name__)
_PRECISION = Decimal("0.000000001")
_SENSITIVE = ("token", "secret", "password", "credential", "api_key", "authorization")


def _decimal(value: Any) -> Decimal:
    return Decimal(str(value))


def _safe_metadata(metadata: Mapping[str, Any] | None) -> dict[str, Any]:
    return {
        key: value for key, value in (metadata or {}).items()
        if not any(part in key.lower() for part in _SENSITIVE)
        and (isinstance(value, (str, int, float, bool)) or value is None)
    }


@dataclass(frozen=True)
class ComputeUnitCalculation:
    status: str
    compute_units: Decimal | None
    policy_id: str | None
    cost_per_compute_unit: Decimal | None
    reason: str | None = None


class ComputeUnitService:
    """Converts priced infrastructure cost into CU. It performs no wallet enforcement."""

    def __init__(self, db: Session):
        self.db = db

    def register_policy(
        self, *, name: str, currency: str, cost_per_compute_unit: Decimal | int | float | str,
        effective_from: datetime | None = None, enabled: bool = True,
        metadata: Mapping[str, Any] | None = None,
    ) -> ComputeUnitPolicy:
        unit_cost = _decimal(cost_per_compute_unit)
        if unit_cost <= 0:
            raise ValueError("cost_per_compute_unit must be greater than zero")
        policy = ComputeUnitPolicy(
            name=name.strip()[:80], currency=currency.strip().upper()[:10],
            cost_per_compute_unit=unit_cost, effective_from=effective_from or utc_now(),
            enabled=enabled, extra_metadata=_safe_metadata(metadata),
        )
        self.db.add(policy)
        self.db.flush()
        return policy

    def resolve(self, *, currency: str, at: datetime | None = None) -> ComputeUnitPolicy | None:
        return (
            self.db.query(ComputeUnitPolicy)
            .filter(
                ComputeUnitPolicy.currency == currency.strip().upper(),
                ComputeUnitPolicy.enabled.is_(True),
                ComputeUnitPolicy.effective_from <= (at or utc_now()),
            )
            .order_by(ComputeUnitPolicy.effective_from.desc())
            .first()
        )

    def calculate(self, *, actual_cost: Decimal | int | float | str | None, currency: str | None, at: datetime | None = None) -> ComputeUnitCalculation:
        if actual_cost is None:
            return ComputeUnitCalculation("unpriced", None, None, None, "cost_unpriced")
        cost = _decimal(actual_cost)
        if cost < 0:
            return ComputeUnitCalculation("error", None, None, None, "negative_cost")
        if cost == 0:
            return ComputeUnitCalculation("free", Decimal("0").quantize(_PRECISION), None, None)
        if not currency:
            return ComputeUnitCalculation("unpriced", None, None, None, "currency_missing")
        policy = self.resolve(currency=currency, at=at)
        if not policy:
            logger.warning("compute_unit_policy_missing currency=%s", currency[:10])
            return ComputeUnitCalculation("policy_missing", None, None, None, "policy_missing")
        unit_cost = _decimal(policy.cost_per_compute_unit)
        if unit_cost <= 0:
            return ComputeUnitCalculation("error", None, policy.id, unit_cost, "invalid_policy")
        units = (cost / unit_cost).quantize(_PRECISION, rounding=ROUND_HALF_UP)
        return ComputeUnitCalculation("calculated", units, policy.id, unit_cost)

    def convert_event(self, event: UsageLedger, *, force: bool = False) -> ComputeUnitCalculation:
        if event.compute_unit_status in {"calculated", "free"} and not force:
            return ComputeUnitCalculation(event.compute_unit_status, _decimal(event.compute_units or 0), event.compute_unit_policy_id, None)
        if event.pricing_status != "priced":
            event.compute_units = None
            event.compute_unit_status = "unpriced"
            event.compute_unit_policy_id = None
            self.db.flush()
            return ComputeUnitCalculation("unpriced", None, None, None, "cost_unpriced")
        calculation = self.calculate(actual_cost=event.actual_cost, currency=event.cost_currency, at=event.created_at)
        event.compute_units = calculation.compute_units
        event.compute_unit_status = calculation.status
        event.compute_unit_policy_id = calculation.policy_id
        if calculation.reason:
            event.extra_metadata = {**(event.extra_metadata or {}), "compute_unit_reason": calculation.reason}
        self.db.flush()
        if calculation.status in {"calculated", "free"}:
            from app.services.compute_wallet_service import ComputeWalletService
            ComputeWalletService(self.db).record_usage(event)
            from app.services.cost_estimator import CostEstimator
            CostEstimator(self.db).reconcile_event(event)
        return calculation
