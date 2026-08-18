from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any, Mapping

from sqlalchemy.orm import Session

from app.models.commercial import ComputeWallet, ResourcePolicy, ResourcePolicyDecision
from app.models.mixins import utc_now
from app.services.capabilities.registry import capability_registry
from app.services.cost_estimator import CostEstimateResult

DECISIONS = {"ALLOW", "ALLOW_LITE", "ALLOW_DEGRADED", "REQUIRE_UPGRADE", "DENY", "UNKNOWN"}
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
class PolicyDecision:
    decision: str
    reason: str
    capability_key: str
    estimated_cu: Decimal | None
    available_cu: Decimal | None
    execution_mode: str
    fallback_mode: str | None
    requires_confirmation: bool
    policy_version: str
    enforced: bool
    effective_behavior: str
    metadata: dict[str, Any]
    record_id: str | None = None


class ResourcePolicyEngine:
    """Resource policy only; permissions, routing, and wallet mutation remain elsewhere."""

    def __init__(self, db: Session):
        self.db = db

    def register_policy(
        self, *, policy_version: str, plan_key: str, warning_threshold: Any,
        degrade_threshold: Any, hard_compute_threshold: Any | None = None,
        lite_enabled: bool = True, observe_only: bool = True,
        allow_negative_shadow: bool = True, enabled: bool = True,
        effective_from: datetime | None = None, metadata: Mapping[str, Any] | None = None,
    ) -> ResourcePolicy:
        warning, degrade = _decimal(warning_threshold), _decimal(degrade_threshold)
        if not (Decimal("0") <= degrade <= warning <= Decimal("1")):
            raise ValueError("thresholds must satisfy 0 <= degrade <= warning <= 1")
        policy = ResourcePolicy(
            policy_version=policy_version[:40], plan_key=plan_key.lower()[:40],
            warning_threshold=warning, degrade_threshold=degrade,
            hard_compute_threshold=_decimal(hard_compute_threshold) if hard_compute_threshold is not None else None,
            lite_enabled=lite_enabled, observe_only=observe_only,
            allow_negative_shadow=allow_negative_shadow, enabled=enabled,
            effective_from=effective_from or utc_now(), extra_metadata=_safe_metadata(metadata),
        )
        self.db.add(policy); self.db.flush()
        return policy

    def resolve_policy(self, *, plan_key: str, at: datetime | None = None) -> ResourcePolicy | None:
        moment = at or utc_now()
        return self.db.query(ResourcePolicy).filter(
            ResourcePolicy.plan_key.in_([plan_key.lower(), "development/default"]),
            ResourcePolicy.enabled.is_(True), ResourcePolicy.effective_from <= moment,
        ).order_by(
            (ResourcePolicy.plan_key == plan_key.lower()).desc(), ResourcePolicy.effective_from.desc(),
        ).first()

    def read_wallet(self, user_id: str, *, at: datetime | None = None) -> ComputeWallet | None:
        moment = at or utc_now()
        return self.db.query(ComputeWallet).filter(
            ComputeWallet.user_id == user_id,
            ComputeWallet.period_start <= moment,
            ComputeWallet.period_end >= moment,
        ).order_by(ComputeWallet.period_start.desc()).first()

    def evaluate(
        self, *, user_id: str, request_id: str, capability_key: str,
        estimate: CostEstimateResult, plan_key: str = "development/default",
        request_context: Mapping[str, Any] | None = None,
    ) -> PolicyDecision:
        context = dict(request_context or {})
        manifest = capability_registry.resolve_manifest(capability_key)
        policy = self.resolve_policy(plan_key=plan_key)
        if not policy:
            existing = self.db.query(ResourcePolicyDecision).filter_by(
                user_id=user_id, request_id=request_id, capability_key=manifest.key,
                policy_version="unconfigured",
            ).first()
            if existing:
                return self._from_row(existing, observe_only=True)
            return self._store(user_id, request_id, estimate, PolicyDecision(
                "UNKNOWN", "policy_missing", manifest.key, estimate.estimated_compute_units, None,
                "EXISTING_BEHAVIOR", None, bool(context.get("requires_confirmation")),
                "unconfigured", False, "EXISTING_BEHAVIOR", {},
            ))
        existing = self.db.query(ResourcePolicyDecision).filter_by(
            user_id=user_id, request_id=request_id, capability_key=manifest.key,
            policy_version=policy.policy_version,
        ).first()
        if existing:
            return self._from_row(existing, observe_only=policy.observe_only)
        wallet = self.read_wallet(user_id)
        available = Decimal(str(wallet.available_cu)) if wallet and wallet.available_cu is not None else None
        estimated = estimate.estimated_compute_units
        confirmation = bool(context.get("requires_confirmation"))
        metadata = {"balance_zone": self._balance_zone(wallet, policy)}

        if estimate.status == "unknown" or estimated is None:
            candidate = ("UNKNOWN", "estimate_unknown", "EXISTING_BEHAVIOR", None)
        elif estimated == 0:
            candidate = ("ALLOW", "zero_cost_capability", "FULL", None)
        elif available is None:
            candidate = ("UNKNOWN", "wallet_allowance_unconfigured", "EXISTING_BEHAVIOR", None)
        elif available >= estimated:
            candidate = ("ALLOW", "compute_available", "FULL", None)
        elif manifest.lite_allowed and not manifest.requires_ai:
            candidate = ("ALLOW", "lite_safe_non_ai", "LITE", "LITE")
        elif manifest.cost_class == "high":
            candidate = ("REQUIRE_UPGRADE", "insufficient_compute_high_cost", "BLOCKED", None)
        elif policy.lite_enabled and manifest.lite_allowed:
            candidate = ("ALLOW_LITE", "insufficient_compute_lite_available", "LITE", "LITE")
        elif policy.lite_enabled and manifest.requires_ai:
            candidate = ("ALLOW_DEGRADED", "insufficient_compute_degradation_candidate", "DEGRADED", "LITE")
        else:
            candidate = ("REQUIRE_UPGRADE", "insufficient_compute", "BLOCKED", None)
        if policy.hard_compute_threshold is not None and estimated is not None and estimated > _decimal(policy.hard_compute_threshold) and candidate[0] == "ALLOW":
            candidate = ("ALLOW_DEGRADED", "hard_compute_threshold_exceeded", "DEGRADED", "LITE" if policy.lite_enabled else None)
        enforced = not policy.observe_only
        effective = candidate[2] if enforced else "EXISTING_BEHAVIOR"
        return self._store(user_id, request_id, estimate, PolicyDecision(
            candidate[0], candidate[1], manifest.key, estimated, available, candidate[2], candidate[3],
            confirmation, policy.policy_version, enforced, effective, metadata,
        ))

    @staticmethod
    def _balance_zone(wallet: ComputeWallet | None, policy: ResourcePolicy) -> str:
        if not wallet or wallet.included_cu is None:
            return "unknown"
        total = _decimal(wallet.included_cu) + _decimal(wallet.bonus_cu)
        available = _decimal(wallet.available_cu)
        if available <= 0 or total <= 0:
            return "exhausted"
        ratio = available / total
        if ratio <= _decimal(policy.degrade_threshold):
            return "critical"
        if ratio <= _decimal(policy.warning_threshold):
            return "low"
        return "healthy"

    def _store(self, user_id: str, request_id: str, estimate: CostEstimateResult, decision: PolicyDecision) -> PolicyDecision:
        row = ResourcePolicyDecision(
            user_id=user_id, request_id=request_id[:120], capability_key=decision.capability_key,
            estimate_id=estimate.estimate_id, decision=decision.decision, reason=decision.reason,
            wallet_available_cu=decision.available_cu, estimated_compute_units=decision.estimated_cu,
            policy_version=decision.policy_version, execution_mode=decision.execution_mode,
            fallback_mode=decision.fallback_mode, requires_confirmation=decision.requires_confirmation,
            enforced=decision.enforced, extra_metadata=_safe_metadata(decision.metadata),
        )
        self.db.add(row); self.db.flush()
        return PolicyDecision(**{**decision.__dict__, "record_id": row.id})

    @staticmethod
    def _from_row(row: ResourcePolicyDecision, *, observe_only: bool) -> PolicyDecision:
        return PolicyDecision(
            row.decision, row.reason, row.capability_key,
            Decimal(str(row.estimated_compute_units)) if row.estimated_compute_units is not None else None,
            Decimal(str(row.wallet_available_cu)) if row.wallet_available_cu is not None else None,
            row.execution_mode, row.fallback_mode, row.requires_confirmation, row.policy_version,
            row.enforced, "EXISTING_BEHAVIOR" if observe_only else row.execution_mode,
            row.extra_metadata or {}, row.id,
        )
