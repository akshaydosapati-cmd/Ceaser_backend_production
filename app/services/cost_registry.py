from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Mapping

from sqlalchemy.orm import Session

from app.models.commercial import ProviderCostRate, UsageLedger
from app.models.mixins import utc_now

logger = logging.getLogger(__name__)

PRICING_UNITS = {
    "per_input_token", "per_output_token", "per_1k_tokens", "per_1m_tokens",
    "per_minute", "per_second", "per_request", "per_search", "per_image",
    "per_tool_call", "fixed", "free",
}
_SENSITIVE = ("token", "secret", "password", "credential", "api_key", "authorization")
_PRECISION = Decimal("0.000000000001")


def _decimal(value: Any) -> Decimal:
    try:
        return max(Decimal("0"), Decimal(str(value or 0)))
    except Exception:
        return Decimal("0")


def _safe_metadata(metadata: Mapping[str, Any] | None) -> dict[str, Any]:
    return {
        key: value for key, value in (metadata or {}).items()
        if not any(part in key.lower() for part in _SENSITIVE)
        and (isinstance(value, (str, int, float, bool)) or value is None)
    }


@dataclass(frozen=True)
class CostCalculation:
    status: str
    amount: Decimal | None
    currency: str | None
    rate_id: str | None
    pricing_unit: str | None
    reason: str | None = None


class CostRegistry:
    """Versioned infrastructure pricing. It never modifies user credit policy."""

    def __init__(self, db: Session):
        self.db = db

    def register(
        self, *, provider: str, service: str, operation: str, pricing_unit: str,
        input_unit_cost: Decimal | int | float | str = 0,
        output_unit_cost: Decimal | int | float | str = 0,
        currency: str = "USD", effective_from: datetime | None = None,
        enabled: bool = True, metadata: Mapping[str, Any] | None = None,
    ) -> ProviderCostRate:
        if pricing_unit not in PRICING_UNITS:
            raise ValueError(f"Unsupported pricing unit: {pricing_unit}")
        rate = ProviderCostRate(
            provider=provider.strip().lower()[:80], service=service.strip().lower()[:80],
            operation=operation.strip().lower()[:120], pricing_unit=pricing_unit,
            input_unit_cost=_decimal(input_unit_cost), output_unit_cost=_decimal(output_unit_cost),
            currency=currency.strip().upper()[:10], effective_from=effective_from or utc_now(),
            enabled=enabled, extra_metadata=_safe_metadata(metadata),
        )
        self.db.add(rate)
        self.db.flush()
        return rate

    def resolve(self, *, provider: str, service: str, operation: str, at: datetime | None = None) -> ProviderCostRate | None:
        return (
            self.db.query(ProviderCostRate)
            .filter(
                ProviderCostRate.provider == provider.strip().lower(),
                ProviderCostRate.service == service.strip().lower(),
                ProviderCostRate.operation == operation.strip().lower(),
                ProviderCostRate.enabled.is_(True),
                ProviderCostRate.effective_from <= (at or utc_now()),
            )
            .order_by(ProviderCostRate.effective_from.desc())
            .first()
        )

    def calculate(self, *, provider: str, service: str, operation: str, usage: Mapping[str, Any], at: datetime | None = None) -> CostCalculation:
        rate = self.resolve(provider=provider, service=service, operation=operation, at=at)
        if not rate:
            logger.warning("cost_registry_unpriced provider=%s service=%s operation=%s", provider[:80], service[:80], operation[:120])
            return CostCalculation("unpriced", None, None, None, None, "unknown_rate")
        amount = self._calculate_rate(rate, usage).quantize(_PRECISION, rounding=ROUND_HALF_UP)
        return CostCalculation("priced", amount, rate.currency, rate.id, rate.pricing_unit)

    def price_event(self, event: UsageLedger, *, service: str | None = None, force: bool = False) -> CostCalculation:
        if event.pricing_status == "priced" and not force:
            calculation = CostCalculation("priced", _decimal(event.actual_cost), event.cost_currency, event.pricing_rate_id, None)
            from app.services.compute_unit_service import ComputeUnitService
            ComputeUnitService(self.db).convert_event(event)
            return calculation
        if not event.provider:
            from app.services.capabilities.registry import capability_registry
            manifest = capability_registry.resolve_manifest(event.capability_key or event.operation)
            if manifest.cost_class == "free" and manifest.execution_type in {"local", "artifact"}:
                event.pricing_status = "priced"
                event.actual_cost = 0
                calculation = CostCalculation("priced", Decimal("0"), None, None, "free", "manifest_free")
                from app.services.compute_unit_service import ComputeUnitService
                ComputeUnitService(self.db).convert_event(event, force=force)
                self.db.flush()
                return calculation
            event.pricing_status = "unpriced"
            event.extra_metadata = {**(event.extra_metadata or {}), "pricing_reason": "provider_missing"}
            calculation = CostCalculation("unpriced", None, None, None, None, "provider_missing")
            from app.services.compute_unit_service import ComputeUnitService
            ComputeUnitService(self.db).convert_event(event)
            return calculation
        calculation = self.calculate(
            provider=event.provider, service=service or event.action_type, operation=event.operation,
            usage={
                "input_tokens": event.input_tokens, "output_tokens": event.output_tokens,
                "voice_seconds": event.voice_seconds, "voice_input_seconds": event.voice_input_seconds,
                "voice_output_seconds": event.voice_output_seconds, "searches": event.web_searches,
                "images": event.image_generations, "tool_calls": event.tool_calls, "requests": event.quantity,
            },
            at=event.created_at,
        )
        event.pricing_status = calculation.status
        event.pricing_rate_id = calculation.rate_id
        event.cost_currency = calculation.currency
        if calculation.amount is not None:
            event.actual_cost = float(calculation.amount)
        else:
            event.extra_metadata = {**(event.extra_metadata or {}), "pricing_reason": calculation.reason}
        from app.services.compute_unit_service import ComputeUnitService
        ComputeUnitService(self.db).convert_event(event, force=force)
        self.db.flush()
        return calculation

    def estimate_event(self, event: UsageLedger, *, usage: Mapping[str, Any], service: str | None = None) -> CostCalculation:
        if not event.provider:
            event.pricing_status = "unpriced"
            event.extra_metadata = {**(event.extra_metadata or {}), "pricing_reason": "provider_missing"}
            return CostCalculation("unpriced", None, None, None, None, "provider_missing")
        calculation = self.calculate(
            provider=event.provider, service=service or event.action_type,
            operation=event.operation, usage=usage, at=event.created_at,
        )
        event.pricing_status = "estimated" if calculation.status == "priced" else "unpriced"
        event.pricing_rate_id = calculation.rate_id
        event.cost_currency = calculation.currency
        if calculation.amount is not None:
            event.estimated_cost = float(calculation.amount)
        else:
            event.extra_metadata = {**(event.extra_metadata or {}), "pricing_reason": calculation.reason}
        self.db.flush()
        return calculation

    @staticmethod
    def _calculate_rate(rate: ProviderCostRate, usage: Mapping[str, Any]) -> Decimal:
        unit = rate.pricing_unit
        input_cost, output_cost = _decimal(rate.input_unit_cost), _decimal(rate.output_unit_cost)
        inputs, outputs = _decimal(usage.get("input_tokens")), _decimal(usage.get("output_tokens"))
        if unit == "free": return Decimal("0")
        if unit == "fixed": return input_cost
        if unit == "per_input_token": return inputs * input_cost
        if unit == "per_output_token": return outputs * (output_cost or input_cost)
        if unit in {"per_1k_tokens", "per_1m_tokens"}:
            divisor = Decimal("1000") if unit == "per_1k_tokens" else Decimal("1000000")
            return (inputs * input_cost + outputs * output_cost) / divisor
        if unit in {"per_minute", "per_second"}:
            divisor = Decimal("60") if unit == "per_minute" else Decimal("1")
            input_seconds = _decimal(usage.get("voice_input_seconds"))
            output_seconds = _decimal(usage.get("voice_output_seconds"))
            if not input_seconds and not output_seconds:
                input_seconds = _decimal(usage.get("voice_seconds"))
            return (input_seconds * input_cost + output_seconds * (output_cost or input_cost)) / divisor
        quantity_key = {"per_request": "requests", "per_search": "searches", "per_image": "images", "per_tool_call": "tool_calls"}[unit]
        default = 1 if unit == "per_request" else 0
        return _decimal(usage.get(quantity_key, default)) * input_cost
