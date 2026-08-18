from decimal import Decimal

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.models  # noqa: F401
from app.core.database.base import Base
from app.models.commercial import ComputeWalletTransaction, UsageEstimate
from app.models.user import User
from app.services.compute_unit_service import ComputeUnitService
from app.services.cost_estimator import CostEstimator
from app.services.cost_registry import CostRegistry
from app.services.usage_ledger_service import UsageLedgerService


engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
Session = sessionmaker(bind=engine)


def test_c6_deterministic_provider_historical_unknown_and_reconciliation():
    Base.metadata.drop_all(engine); Base.metadata.create_all(engine)
    db = Session(); user = User(email="estimator-c6@ceaser.local"); db.add(user); db.commit()
    ComputeUnitService(db).register_policy(name="test", currency="USD", cost_per_compute_unit="0.01")
    rates = CostRegistry(db)
    rates.register(provider="github", service="github", operation="github.list_issues", pricing_unit="per_request", input_unit_cost="0.001")
    rates.register(provider="openai", service="document", operation="document.generate_content", pricing_unit="per_1k_tokens", input_unit_cost="0.002", output_unit_cost="0.008")
    rates.register(provider="speech", service="voice", operation="voice.transcribe", pricing_unit="per_minute", input_unit_cost="0.006")
    rates.register(provider="openai", service="voice", operation="chat.answer", pricing_unit="per_1k_tokens", input_unit_cost="0.002", output_unit_cost="0.008")
    rates.register(provider="speech", service="voice", operation="voice.synthesize", pricing_unit="per_minute", output_unit_cost="0.012")
    db.commit(); estimator = CostEstimator(db)

    local = estimator.estimate(user_id=user.id, request_id="local", capability_key="applications.open")
    assert local.estimated_compute_units == Decimal("0") and local.confidence == "high" and local.basis == "manifest/free"
    github = estimator.estimate(user_id=user.id, request_id="github", capability_key="github.list_issues", request_context={"provider": "github", "service": "github"})
    assert github.estimated_compute_units == Decimal("0.100000000") and github.confidence == "high"
    document = estimator.estimate(user_id=user.id, request_id="doc", capability_key="document.generate_content", request_context={"provider": "openai", "service": "document", "input_tokens": 1000, "expected_output_tokens": 2000})
    assert document.estimated_compute_units == Decimal("1.800000000") and document.confidence == "medium"
    voice = estimator.estimate(user_id=user.id, request_id="voice", capability_key="voice.ai_conversation", request_context={"components": [
        {"label": "STT", "provider": "speech", "service": "voice", "operation": "voice.transcribe", "usage": {"voice_input_seconds": 30}},
        {"label": "AI", "provider": "openai", "service": "voice", "operation": "chat.answer", "usage": {"input_tokens": 500, "output_tokens": 500}},
        {"label": "TTS", "provider": "speech", "service": "voice", "operation": "voice.synthesize", "usage": {"voice_output_seconds": 20}},
    ]})
    assert voice.status == "estimated" and voice.confidence == "medium" and set(voice.breakdown) >= {"STT", "AI", "TTS", "total"}
    unknown = estimator.estimate(user_id=user.id, request_id="unknown", capability_key="unknown.capability")
    assert unknown.status == "unknown" and unknown.estimated_compute_units is None

    # Historical P75 is segmented by the request bucket and needs at least three samples.
    for index, units in enumerate((10, 20, 30, 100)):
        event = UsageLedgerService(db).start(user_id=user.id, request_id=f"hist-{index}", feature="workforce", operation="workforce.run_job", metadata={"estimate_bucket": "standard"})
        event.compute_unit_status = "calculated"; event.compute_units = units
    historical = estimator.estimate(user_id=user.id, request_id="workforce", capability_key="workforce.run_job", request_context={"complexity_hint": "standard"})
    assert historical.basis == "historical_p75" and historical.estimated_compute_units == Decimal("30.000000000")

    before = db.query(ComputeWalletTransaction).count()
    estimate = estimator.estimate(user_id=user.id, request_id="actual", capability_key="document.generate_content", request_context={"provider": "openai", "service": "document", "input_tokens": 1000, "expected_output_tokens": 2000})
    event = UsageLedgerService(db).start(user_id=user.id, request_id="actual", feature="document", operation="document.generate_content", provider="openai")
    UsageLedgerService(db).complete(event, input_tokens=1000, output_tokens=1000)
    row = db.query(UsageEstimate).filter_by(id=estimate.estimate_id).one()
    assert row.actual_compute_units is not None and row.variance_percent is not None
    assert db.query(ComputeWalletTransaction).count() == before + 1  # Actual C4 debit only; C6 never mutates wallet.
    db.close()
