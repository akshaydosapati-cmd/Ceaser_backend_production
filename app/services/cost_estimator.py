from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Mapping

from sqlalchemy.orm import Session

from app.models.commercial import UsageEstimate, UsageLedger
from app.services.capabilities.registry import capability_registry
from app.services.compute_unit_service import ComputeUnitService
from app.services.cost_registry import CostRegistry

_CU_PRECISION = Decimal("0.000000001")
_COST_PRECISION = Decimal("0.000000000001")
ESTIMATOR_VERSION = "c6-v1"


def _decimal(value: Any) -> Decimal:
    return Decimal(str(value or 0))


@dataclass(frozen=True)
class CostEstimateResult:
    capability_key: str
    estimated_cost: Decimal | None
    cost_currency: str | None
    estimated_compute_units: Decimal | None
    confidence: str
    cost_class: str
    basis: str
    breakdown: dict[str, str]
    status: str
    estimator_version: str = ESTIMATOR_VERSION
    estimate_id: str | None = None


class CostEstimator:
    """Predictive accounting only. It never reserves, debits, or authorizes."""

    def __init__(self, db: Session):
        self.db = db

    @staticmethod
    def context_bucket(context: Mapping[str, Any]) -> str:
        hint = str(context.get("complexity_hint") or "").lower()
        if hint in {"small", "medium", "large", "light", "standard", "deep"}:
            return hint
        tokens = int(context.get("expected_output_tokens") or 0) + int(context.get("input_tokens") or 0)
        files = int(context.get("file_count") or 0)
        size = int(context.get("file_size") or 0)
        agents = int(context.get("agent_count") or 0)
        if tokens > 10_000 or files > 10 or size > 10_000_000 or agents > 3:
            return "large"
        if tokens > 2_000 or files > 2 or size > 1_000_000 or agents > 1:
            return "medium"
        return "small"

    def estimate(
        self, *, user_id: str, request_id: str, capability_key: str,
        request_context: Mapping[str, Any] | None = None, persist: bool = True,
    ) -> CostEstimateResult:
        context = dict(request_context or {})
        manifest = capability_registry.resolve_manifest(capability_key)
        bucket = self.context_bucket(context)
        existing = self.db.query(UsageEstimate).filter_by(
            user_id=user_id, request_id=request_id, capability_key=manifest.key,
            estimator_version=ESTIMATOR_VERSION,
        ).first()
        if existing:
            return self._from_row(existing)

        # Local/free resolution is intentionally before historical or provider queries.
        if manifest.cost_class == "free":
            result = CostEstimateResult(manifest.key, Decimal("0"), None, Decimal("0"), "high", manifest.cost_class, "manifest/free", {"local_execution": "0"}, "estimated")
        elif manifest.cost_class == "unknown" or manifest.execution_type == "unknown":
            result = CostEstimateResult(manifest.key, None, None, None, "unknown", manifest.cost_class, "unknown_capability", {}, "unknown")
        else:
            result = self._provider_estimate(manifest.key, manifest.cost_class, context)
            if result.status == "unknown":
                historical = self._historical_estimate(manifest.key, manifest.cost_class, bucket)
                if historical is not None:
                    result = historical
        if persist:
            result = self._persist(user_id, request_id, bucket, result)
        return result

    def estimate_with_policy(
        self, *, user_id: str, request_id: str, capability_key: str,
        request_context: Mapping[str, Any] | None = None,
        plan_key: str = "development/default",
    ):
        estimate = self.estimate(
            user_id=user_id, request_id=request_id, capability_key=capability_key,
            request_context=request_context, persist=True,
        )
        from app.services.resource_policy_engine import ResourcePolicyEngine
        decision = ResourcePolicyEngine(self.db).evaluate(
            user_id=user_id, request_id=request_id, capability_key=capability_key,
            estimate=estimate, plan_key=plan_key, request_context=request_context,
        )
        return estimate, decision

    def resolve_execution(
        self, *, user_id: str, request_id: str, capability_key: str,
        arguments: Mapping[str, Any] | None = None,
        request_context: Mapping[str, Any] | None = None,
        plan_key: str = "development/default", rollout_mode: str = "observe",
    ):
        estimate, decision = self.estimate_with_policy(
            user_id=user_id, request_id=request_id, capability_key=capability_key,
            request_context=request_context, plan_key=plan_key,
        )
        from app.services.lite_behavior import LiteExecutionResolver
        resolution = LiteExecutionResolver(self.db).resolve(
            policy_decision=decision, capability_key=capability_key, arguments=arguments,
            rollout_mode=rollout_mode, request_context=request_context,
        )
        return estimate, decision, resolution

    def _provider_estimate(self, capability_key: str, cost_class: str, context: Mapping[str, Any]) -> CostEstimateResult:
        components = list(context.get("components") or [])
        if not components and context.get("provider"):
            components = [{
                "label": context.get("label") or capability_key,
                "provider": context["provider"], "service": context.get("service") or capability_key.split(".", 1)[0],
                "operation": context.get("operation") or capability_key,
                "usage": self._usage(context),
            }]
        if not components:
            return CostEstimateResult(capability_key, None, None, None, "unknown", cost_class, "pricing_context_missing", {}, "unknown")
        total = Decimal("0")
        currency = None
        breakdown: dict[str, str] = {}
        for index, component in enumerate(components):
            calculation = CostRegistry(self.db).calculate(
                provider=str(component.get("provider") or ""), service=str(component.get("service") or ""),
                operation=str(component.get("operation") or ""), usage=component.get("usage") or {},
            )
            if calculation.status != "priced" or calculation.amount is None:
                return CostEstimateResult(capability_key, None, None, None, "unknown", cost_class, "provider_rate_missing", breakdown, "unknown")
            if currency and calculation.currency != currency:
                return CostEstimateResult(capability_key, None, None, None, "unknown", cost_class, "mixed_currency", breakdown, "unknown")
            currency = calculation.currency
            total += calculation.amount
            breakdown[str(component.get("label") or f"component_{index + 1}")] = str(calculation.amount)
        converted = ComputeUnitService(self.db).calculate(actual_cost=total, currency=currency)
        if converted.compute_units is None:
            return CostEstimateResult(capability_key, total, currency, None, "unknown", cost_class, converted.reason or "conversion_unavailable", breakdown, "unknown")
        confidence = "high" if len(components) == 1 and cost_class in {"negligible", "low"} else "medium"
        if cost_class == "high" or len(components) > 3:
            confidence = "low"
        breakdown["total"] = str(total.quantize(_COST_PRECISION, rounding=ROUND_HALF_UP))
        return CostEstimateResult(capability_key, total.quantize(_COST_PRECISION), currency, converted.compute_units, confidence, cost_class, "provider_rates", breakdown, "estimated")

    @staticmethod
    def _usage(context: Mapping[str, Any]) -> dict[str, Any]:
        return {
            "input_tokens": context.get("input_tokens", 0),
            "output_tokens": context.get("expected_output_tokens", context.get("output_tokens", 0)),
            "voice_input_seconds": context.get("voice_input_seconds", context.get("voice_seconds", 0)),
            "voice_output_seconds": context.get("voice_output_seconds", 0),
            "searches": context.get("search_count", 0), "images": context.get("image_count", 0),
            "tool_calls": context.get("tool_calls", 0), "requests": context.get("requests", 1),
        }

    def _historical_estimate(self, capability_key: str, cost_class: str, bucket: str) -> CostEstimateResult | None:
        rows = self.db.query(UsageLedger).filter(
            UsageLedger.capability_key == capability_key,
            UsageLedger.compute_unit_status.in_(["calculated", "free"]),
            UsageLedger.compute_units.isnot(None),
        ).order_by(UsageLedger.created_at.desc()).limit(100).all()
        values = sorted(
            _decimal(row.compute_units) for row in rows
            if str((row.extra_metadata or {}).get("estimate_bucket") or "small") == bucket
        )
        if len(values) < 3:
            return None
        index = max(0, min(len(values) - 1, ((len(values) * 75 + 99) // 100) - 1))
        p75 = values[index].quantize(_CU_PRECISION, rounding=ROUND_HALF_UP)
        return CostEstimateResult(capability_key, None, None, p75, "medium", cost_class, "historical_p75", {"sample_count": str(len(values)), "p75_cu": str(p75)}, "estimated")

    def _persist(self, user_id: str, request_id: str, bucket: str, result: CostEstimateResult) -> CostEstimateResult:
        row = UsageEstimate(
            user_id=user_id, request_id=request_id[:120], capability_key=result.capability_key,
            context_bucket=bucket, estimated_cost=result.estimated_cost, cost_currency=result.cost_currency,
            estimated_compute_units=result.estimated_compute_units, confidence=result.confidence,
            cost_class=result.cost_class, status=result.status, estimator_version=result.estimator_version,
            basis=result.basis, breakdown=result.breakdown,
        )
        self.db.add(row)
        self.db.flush()
        return CostEstimateResult(**{**result.__dict__, "estimate_id": row.id})

    def reconcile_event(self, event: UsageLedger) -> UsageEstimate | None:
        if not event.request_id or event.compute_units is None:
            return None
        row = self.db.query(UsageEstimate).filter_by(user_id=event.user_id, request_id=event.request_id).order_by(UsageEstimate.created_at.desc()).first()
        if not row or row.actual_compute_units is not None:
            return row
        actual = _decimal(event.compute_units).quantize(_CU_PRECISION)
        row.usage_ledger_id = event.id
        row.actual_compute_units = actual
        estimated = _decimal(row.estimated_compute_units) if row.estimated_compute_units is not None else None
        row.variance_percent = None if estimated in {None, Decimal("0")} else ((actual - estimated) / estimated * 100).quantize(Decimal("0.0001"))
        self.db.flush()
        return row

    @staticmethod
    def _from_row(row: UsageEstimate) -> CostEstimateResult:
        return CostEstimateResult(
            row.capability_key, Decimal(str(row.estimated_cost)) if row.estimated_cost is not None else None,
            row.cost_currency, Decimal(str(row.estimated_compute_units)) if row.estimated_compute_units is not None else None,
            row.confidence, row.cost_class, row.basis, row.breakdown or {}, row.status, row.estimator_version, row.id,
        )
