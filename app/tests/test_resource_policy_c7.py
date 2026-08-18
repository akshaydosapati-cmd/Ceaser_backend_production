from decimal import Decimal

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.models  # noqa: F401
from app.core.database.base import Base
from app.models.commercial import ComputeWallet, ComputeWalletTransaction, ResourcePolicyDecision
from app.models.mixins import utc_now
from app.models.user import User
from app.services.cost_estimator import CostEstimateResult
from app.services.resource_policy_engine import ResourcePolicyEngine


engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
Session = sessionmaker(bind=engine)


def estimate(key, cu, status="estimated"):
    return CostEstimateResult(key, None, None, Decimal(str(cu)) if cu is not None else None, "medium" if cu is not None else "unknown", "variable", "test", {}, status, estimate_id=None)


def test_c7_shadow_policy_scenarios_are_idempotent_and_read_only():
    Base.metadata.drop_all(engine); Base.metadata.create_all(engine)
    db = Session(); user = User(email="policy-c7@ceaser.local"); db.add(user); db.commit()
    engine_service = ResourcePolicyEngine(db)
    engine_service.register_policy(policy_version="development-v1", plan_key="development/default", warning_threshold="0.30", degrade_threshold="0.10", hard_compute_threshold=None, observe_only=True)
    now = utc_now(); wallet = ComputeWallet(user_id=user.id, plan_key="development/default", period_start=now.replace(day=1), period_end=now.replace(day=28, hour=23, minute=59), included_cu=100, bonus_cu=0, used_cu=0, reserved_cu=0)
    db.add(wallet); db.commit()

    scenarios = [
        ("full-local", "applications.open", 0, "ALLOW"),
        ("full-ai", "document.generate_content", 20, "ALLOW"),
    ]
    for request_id, key, cu, expected in scenarios:
        result = engine_service.evaluate(user_id=user.id, request_id=request_id, capability_key=key, estimate=estimate(key, cu))
        assert result.decision == expected and result.effective_behavior == "EXISTING_BEHAVIOR" and not result.enforced

    wallet.used_cu = 85; db.commit()
    affordable = engine_service.evaluate(user_id=user.id, request_id="low-affordable", capability_key="document.generate_content", estimate=estimate("document.generate_content", 10))
    assert affordable.decision == "ALLOW" and affordable.metadata["balance_zone"] == "low"
    deletion = engine_service.evaluate(user_id=user.id, request_id="delete", capability_key="files.delete", estimate=estimate("files.delete", 0), request_context={"requires_confirmation": True})
    assert deletion.decision == "ALLOW" and deletion.requires_confirmation

    wallet.used_cu = 100; db.commit()
    exhausted = [
        ("zero-local", "applications.open", 0, "ALLOW"),
        ("zero-voice", "voice.simple_command", 0, "ALLOW"),
        ("zero-github", "github.list_issues", Decimal("0.1"), "ALLOW"),
        ("zero-doc", "document.generate_content", 10, "ALLOW_DEGRADED"),
        ("zero-workforce", "workforce.run_job", 250, "REQUIRE_UPGRADE"),
    ]
    for request_id, key, cu, expected in exhausted:
        result = engine_service.evaluate(user_id=user.id, request_id=request_id, capability_key=key, estimate=estimate(key, cu), request_context={"requires_confirmation": key == "files.delete"})
        assert result.decision == expected
    unknown_capability = engine_service.evaluate(user_id=user.id, request_id="unknown-cap", capability_key="future.action", estimate=estimate("future.action", None, "unknown"))
    unknown_estimate = engine_service.evaluate(user_id=user.id, request_id="unknown-est", capability_key="document.generate_content", estimate=estimate("document.generate_content", None, "unknown"))
    assert unknown_capability.decision == unknown_estimate.decision == "UNKNOWN"

    before_wallets = db.query(ComputeWallet).count(); before_transactions = db.query(ComputeWalletTransaction).count()
    first = engine_service.evaluate(user_id=user.id, request_id="retry", capability_key="workforce.run_job", estimate=estimate("workforce.run_job", 250))
    second = engine_service.evaluate(user_id=user.id, request_id="retry", capability_key="workforce.run_job", estimate=estimate("workforce.run_job", 250))
    assert first.record_id == second.record_id
    assert db.query(ResourcePolicyDecision).filter_by(request_id="retry").count() == 1
    assert db.query(ComputeWallet).count() == before_wallets and db.query(ComputeWalletTransaction).count() == before_transactions
    db.close()
