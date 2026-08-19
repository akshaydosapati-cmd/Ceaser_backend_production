from concurrent.futures import ThreadPoolExecutor
from calendar import monthrange
from decimal import Decimal
from pathlib import Path
from tempfile import TemporaryDirectory

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import app.models  # noqa: F401
from app.core.database.base import Base
from app.models.commercial import ComputeWallet, ComputeWalletTransaction, ResourcePolicyDecision, UsageEstimate, UsageLedger
from app.models.mixins import utc_now
from app.models.user import User
from app.services.compute_unit_service import ComputeUnitService
from app.services.compute_wallet_service import ComputeWalletService
from app.services.cost_estimator import CostEstimator
from app.services.cost_registry import CostRegistry
from app.services.resource_policy_engine import ResourcePolicyEngine
from app.services.usage_ledger_service import UsageLedgerService


def setup_database(url="sqlite://"):
    engine = create_engine(url, connect_args={"check_same_thread": False, "timeout": 30})
    Base.metadata.drop_all(engine); Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    db = Session(); user = User(email=f"c85-{id(engine)}@ceaser.local"); db.add(user); db.commit()
    ComputeUnitService(db).register_policy(name="c85", currency="USD", cost_per_compute_unit="0.01")
    ResourcePolicyEngine(db).register_policy(
        policy_version="c85-observe-v1", plan_key="development/default",
        warning_threshold="0.30", degrade_threshold="0.10", observe_only=True,
    )
    rates = CostRegistry(db)
    rates.register(provider="openai", service="chat", operation="chat.answer", pricing_unit="per_1k_tokens", input_unit_cost="0.002", output_unit_cost="0.008")
    rates.register(provider="openai", service="document", operation="document.generate_content", pricing_unit="per_1k_tokens", input_unit_cost="0.002", output_unit_cost="0.008")
    rates.register(provider="github", service="github", operation="github.list_issues", pricing_unit="per_request", input_unit_cost="0.001")
    rates.register(provider="notion", service="notion", operation="notion.read_page", pricing_unit="per_request", input_unit_cost="0.001")
    db.commit()
    return engine, Session, db, user


def wallet(db, user, included=100, used=0):
    now = utc_now()
    row = ComputeWallet(
        user_id=user.id, plan_key="development/default", period_start=now.replace(day=1, hour=0, minute=0, second=0, microsecond=0),
        period_end=now.replace(day=monthrange(now.year, now.month)[1], hour=23, minute=59, second=59, microsecond=999999), included_cu=included,
        bonus_cu=0, used_cu=used, reserved_cu=0,
    )
    db.add(row); db.commit(); return row


def test_c8_5_end_to_end_resource_intelligence_and_final_cu_transition():
    engine, Session, db, user = setup_database(); wallet(db, user)
    estimator = CostEstimator(db)

    # 1 + 14: normal AI request, actual settlement, reconciliation, and replay idempotency.
    estimate, policy, resolution = estimator.resolve_execution(
        user_id=user.id, request_id="normal-ai", capability_key="chat.answer",
        request_context={"provider": "openai", "service": "chat", "input_tokens": 1000, "expected_output_tokens": 1000},
        rollout_mode="selective_enforce",
    )
    assert policy.decision == "ALLOW" and resolution.should_execute
    event = UsageLedgerService(db).start(user_id=user.id, request_id="normal-ai", feature="chat", operation="chat.answer", provider="openai")
    UsageLedgerService(db).complete(event, input_tokens=1000, output_tokens=1000)
    db.commit(); db.refresh(event)
    assert event.capability_key == "chat.answer" and event.actual_cost == 0.01 and event.compute_units == Decimal("1.000000000")
    estimate_row = db.query(UsageEstimate).filter_by(id=estimate.estimate_id).one()
    assert estimate_row.actual_compute_units == Decimal("1.000000000") and estimate_row.variance_percent == Decimal("0.0000")
    assert db.query(ComputeWalletTransaction).filter_by(reference_id=event.id).count() == 1
    UsageLedgerService(db).complete(event, input_tokens=1000, output_tokens=1000); db.commit()
    assert db.query(UsageLedger).filter_by(request_id="normal-ai").count() == 1
    assert db.query(ComputeWalletTransaction).filter_by(reference_id=event.id).count() == 1
    assert db.query(ResourcePolicyDecision).filter_by(request_id="normal-ai").count() == 1

    # 2-5: known local actions are deterministically free, remain executable, and preserve confirmation.
    for index, (key, confirmation) in enumerate((("applications.open", False), ("voice.simple_command", False), ("files.delete", True), ("browser.control", False), ("clipboard.write", False))):
        _, decision, resolved = estimator.resolve_execution(
            user_id=user.id, request_id=f"local-{index}", capability_key=key,
            request_context={"requires_confirmation": confirmation}, rollout_mode="selective_enforce",
        )
        local_event = UsageLedgerService(db).start(user_id=user.id, request_id=f"local-{index}", feature="native", operation=key)
        UsageLedgerService(db).complete(local_event)
        assert decision.decision == "ALLOW" and resolved.should_execute
        assert resolved.requires_confirmation == confirmation
        assert local_event.pricing_status == "priced" and local_event.compute_unit_status == "free" and local_event.compute_units == Decimal("0E-9")

    # 6-7: Lite-safe plugin reads continue without AI calls.
    for key, provider in (("github.list_issues", "github"), ("notion.read_page", "notion")):
        _, decision, resolved = estimator.resolve_execution(
            user_id=user.id, request_id=key, capability_key=key,
            request_context={"provider": provider, "service": provider}, rollout_mode="selective_enforce",
        )
        assert decision.decision == "ALLOW" and resolved.should_execute and resolved.lite_action == "PLUGIN_ONLY"

    # 8-12: supplied document fallback, expensive AI/workforce handling, and unknown safety.
    exhausted = db.query(ComputeWallet).filter_by(user_id=user.id).one(); exhausted.used_cu = exhausted.included_cu; db.commit()
    _, _, supplied = estimator.resolve_execution(user_id=user.id, request_id="supplied-doc", capability_key="document.generate_content", request_context={"provider": "openai", "service": "document", "input_tokens": 500, "expected_output_tokens": 500, "content_supplied": True}, rollout_mode="selective_enforce")
    _, _, generated = estimator.resolve_execution(user_id=user.id, request_id="generated-doc", capability_key="document.generate_content", request_context={"provider": "openai", "service": "document", "input_tokens": 500, "expected_output_tokens": 500}, rollout_mode="selective_enforce")
    # A concrete non-zero estimate is supplied because no reduced voice provider is configured.
    voice_estimate = estimator.estimate(user_id=user.id, request_id="voice-ai", capability_key="voice.ai_conversation", request_context={"provider": "openai", "service": "chat", "operation": "chat.answer", "input_tokens": 500, "expected_output_tokens": 500})
    voice_policy = ResourcePolicyEngine(db).evaluate(user_id=user.id, request_id="voice-ai", capability_key="voice.ai_conversation", estimate=voice_estimate)
    from app.services.lite_behavior import LiteExecutionResolver
    voice = LiteExecutionResolver(db).resolve(policy_decision=voice_policy, capability_key="voice.ai_conversation", rollout_mode="selective_enforce")
    workforce_estimate = estimator.estimate(user_id=user.id, request_id="workforce", capability_key="workforce.run_job", request_context={"components": [{"label": "planning", "provider": "openai", "service": "chat", "operation": "chat.answer", "usage": {"input_tokens": 1000, "output_tokens": 2000}}]})
    workforce_policy = ResourcePolicyEngine(db).evaluate(user_id=user.id, request_id="workforce", capability_key="workforce.run_job", estimate=workforce_estimate)
    workforce = LiteExecutionResolver(db).resolve(policy_decision=workforce_policy, capability_key="workforce.run_job", rollout_mode="selective_enforce")
    _, unknown_policy, unknown = estimator.resolve_execution(user_id=user.id, request_id="unknown", capability_key="future.action", rollout_mode="selective_enforce")
    assert supplied.should_execute and supplied.effective_capability == "document.create_file"
    assert not generated.should_execute and generated.upgrade_prompted
    assert not voice.should_execute and voice.upgrade_prompted
    assert workforce_policy.decision == "REQUIRE_UPGRADE" and not workforce.should_execute
    assert unknown_policy.decision == "UNKNOWN" and unknown.should_execute and unknown.effective_execution_mode == "EXISTING_BEHAVIOR"

    # 13: unpriced is null/unknown, never zero/free.
    unpriced = UsageLedgerService(db).start(user_id=user.id, request_id="unpriced", feature="chat", operation="chat.answer", provider="missing-provider")
    UsageLedgerService(db).complete(unpriced, input_tokens=10, output_tokens=10)
    assert unpriced.pricing_status == "unpriced" and unpriced.compute_units is None and unpriced.compute_unit_status == "unpriced"

    # 16: consuming the final CU never disables local/simple/plugin behavior, while Workforce stops pre-execution.
    exhausted.used_cu = Decimal("99"); db.commit()
    final = UsageLedgerService(db).start(user_id=user.id, request_id="final-cu", feature="chat", operation="chat.answer", provider="openai")
    UsageLedgerService(db).complete(final, input_tokens=1000, output_tokens=1000); db.commit(); db.refresh(exhausted)
    assert exhausted.available_cu == Decimal("0E-9")
    for key in ("applications.open", "voice.simple_command"):
        _, d, r = estimator.resolve_execution(user_id=user.id, request_id=f"after-{key}", capability_key=key, rollout_mode="selective_enforce")
        assert d.decision == "ALLOW" and r.should_execute
    _, d, r = estimator.resolve_execution(user_id=user.id, request_id="after-github", capability_key="github.list_issues", request_context={"provider": "github", "service": "github"}, rollout_mode="selective_enforce")
    assert d.decision == "ALLOW" and r.should_execute
    assert not workforce.should_execute
    db.close(); engine.dispose()


def test_c8_5_concurrent_wallet_updates_are_atomic():
    with TemporaryDirectory() as directory:
        path = Path(directory) / "wallet.db"
        engine, Session, db, user = setup_database(f"sqlite:///{path.as_posix()}"); wallet(db, user, included=100)
        user_id = user.id; db.close()

        def debit(index, amount):
            session = Session()
            event = UsageLedger(user_id=user_id, action_type=("chat", "voice", "plugin")[index], operation=f"concurrent.{index}", status="completed", compute_unit_status="calculated", compute_units=amount, request_id=f"concurrent-{index}", idempotency_key=f"concurrent-{index}", extra_metadata={})
            session.add(event); session.flush(); ComputeWalletService(session).record_usage(event); session.commit(); session.close()

        with ThreadPoolExecutor(max_workers=3) as pool:
            list(pool.map(lambda args: debit(*args), enumerate((1, 2, 3))))
        check = Session(); row = check.query(ComputeWallet).filter_by(user_id=user_id).one()
        assert row.used_cu == Decimal("6.000000000")
        assert check.query(ComputeWalletTransaction).count() == 3
        check.close(); engine.dispose()
