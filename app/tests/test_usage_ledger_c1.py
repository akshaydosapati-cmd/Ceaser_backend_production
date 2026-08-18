from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.models  # noqa: F401 - register all model relationships
from app.core.database.base import Base
from app.models.commercial import UsageLedger
from app.models.user import User
from app.services.credit_service import CreditService
from app.services.usage_ledger_service import UsageLedgerService


engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
Session = sessionmaker(bind=engine)


def test_c1_usage_ledger_and_credit_lifecycle():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    db = Session()
    user = User(email="usage-c1@ceaser.local")
    db.add(user)
    db.commit()

    ledger = UsageLedgerService(db)
    event = ledger.start(
        user_id=user.id,
        request_id="request-1",
        feature="voice",
        operation="voice.answer",
        provider="google",
        model="speech-v2",
        estimated_cost=0.25,
        metadata={"language": "en-IN", "api_key": "must-not-persist", "access_token": "secret"},
    )
    assert ledger.start(user_id=user.id, request_id="request-1", feature="voice", operation="voice.answer").id == event.id
    ledger.complete(
        event,
        input_tokens=120,
        output_tokens=40,
        voice_input_seconds=4,
        voice_output_seconds=7,
        web_searches=1,
        image_generations=2,
        tool_calls=3,
        actual_cost=0.2,
        metadata={"route": "cloud", "refresh_token": "must-not-persist"},
    )
    db.commit()
    db.refresh(event)
    assert event.status == "completed"
    assert (event.input_tokens, event.output_tokens, event.voice_seconds) == (120, 40, 11)
    assert (event.web_searches, event.image_generations, event.tool_calls) == (1, 2, 3)
    assert event.actual_cost == 0.2 and event.compute_units is None
    assert event.compute_unit_status == "unpriced"
    assert event.extra_metadata["language"] == "en-IN"
    assert event.extra_metadata["route"] == "cloud"
    assert event.extra_metadata["pricing_reason"] == "unknown_rate"
    assert "api_key" not in event.extra_metadata and "refresh_token" not in event.extra_metadata

    credits = CreditService(db)
    reservation = credits.reserve(user.id, "chat-request", "ai_conversation")
    started = db.query(UsageLedger).filter_by(request_id="chat-request").one()
    assert started.action_type == "chat" and started.status == "started"
    credits.settle(user.id, "chat-request", reservation.estimated_credits, meaningful_output=True)
    db.refresh(started)
    assert started.status == "completed"
    assert started.compute_units is None
    assert db.query(UsageLedger).filter_by(request_id="chat-request").count() == 1
    db.close()
