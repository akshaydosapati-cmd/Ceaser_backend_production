from datetime import timedelta
from decimal import Decimal

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.models  # noqa: F401
from app.core.database.base import Base
from app.models.user import User
from app.models.mixins import utc_now
from app.services.cost_registry import CostRegistry
from app.services.usage_ledger_service import UsageLedgerService


engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
Session = sessionmaker(bind=engine)


def test_c2_versioned_cost_registry_and_safe_fallback():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    db = Session()
    user = User(email="cost-c2@ceaser.local")
    db.add(user)
    db.commit()
    registry = CostRegistry(db)
    old = utc_now() - timedelta(days=2)
    current = utc_now() - timedelta(days=1)
    registry.register(
        provider="openai", service="chat", operation="chat.generate", pricing_unit="per_1m_tokens",
        input_unit_cost="2", output_unit_cost="8", currency="USD", effective_from=old,
        metadata={"source": "configured", "api_key": "must-not-persist"},
    )
    latest = registry.register(
        provider="openai", service="chat", operation="chat.generate", pricing_unit="per_1m_tokens",
        input_unit_cost="3", output_unit_cost="9", currency="USD", effective_from=current,
    )
    db.commit()
    assert latest.extra_metadata == {}

    result = registry.calculate(
        provider="openai", service="chat", operation="chat.generate",
        usage={"input_tokens": 1_000_000, "output_tokens": 500_000},
    )
    assert result.status == "priced"
    assert result.amount == Decimal("7.500000000000")
    historical = registry.calculate(
        provider="openai", service="chat", operation="chat.generate",
        usage={"input_tokens": 1_000_000, "output_tokens": 500_000}, at=old + timedelta(hours=1),
    )
    assert historical.amount == Decimal("6.000000000000")

    units = {
        "per_input_token": ({"input_tokens": 2}, "2"),
        "per_output_token": ({"output_tokens": 2}, "2"),
        "per_1k_tokens": ({"input_tokens": 1000, "output_tokens": 1000}, "2"),
        "per_minute": ({"voice_seconds": 60}, "1"),
        "per_second": ({"voice_seconds": 2}, "2"),
        "per_request": ({"requests": 2}, "2"),
        "per_search": ({"searches": 2}, "2"),
        "per_image": ({"images": 2}, "2"),
        "per_tool_call": ({"tool_calls": 2}, "2"),
        "fixed": ({}, "1"),
        "free": ({}, "0"),
    }
    for index, (unit, (usage, expected)) in enumerate(units.items()):
        operation = f"unit-{index}"
        registry.register(provider="test", service="test", operation=operation, pricing_unit=unit, input_unit_cost=1, output_unit_cost=1)
        calculated = registry.calculate(provider="test", service="test", operation=operation, usage=usage)
        assert calculated.amount == Decimal(expected).quantize(Decimal("0.000000000001"))

    event = UsageLedgerService(db).start(user_id=user.id, request_id="priced-request", feature="chat", operation="chat.generate", provider="openai")
    UsageLedgerService(db).complete(event, input_tokens=1_000_000, output_tokens=500_000)
    assert event.pricing_status == "priced"
    assert event.pricing_rate_id == latest.id
    assert event.cost_currency == "USD" and event.actual_cost == 7.5

    unknown = registry.calculate(provider="unknown", service="chat", operation="chat.generate", usage={"requests": 1})
    assert unknown.status == "unpriced" and unknown.amount is None
    db.commit()
    db.close()
