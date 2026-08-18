from datetime import timedelta
from decimal import Decimal

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.models  # noqa: F401
from app.core.database.base import Base
from app.models.mixins import utc_now
from app.models.user import User
from app.services.compute_unit_service import ComputeUnitService
from app.services.usage_ledger_service import UsageLedgerService


engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
Session = sessionmaker(bind=engine)


def test_c3_compute_units_historical_zero_unpriced_and_idempotent():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    db = Session()
    user = User(email="compute-c3@ceaser.local")
    db.add(user)
    db.commit()
    service = ComputeUnitService(db)
    old_at = utc_now() - timedelta(days=2)
    new_at = utc_now() - timedelta(days=1)
    old_policy = service.register_policy(name="launch", currency="INR", cost_per_compute_unit="0.01", effective_from=old_at, metadata={"note": "launch", "secret": "hidden"})
    service.register_policy(name="current", currency="INR", cost_per_compute_unit="0.02", effective_from=new_at)
    db.commit()
    assert old_policy.extra_metadata == {"note": "launch"}

    # Four concrete accounting cases: paid, tiny paid, free/local, and unpriced.
    paid = service.calculate(actual_cost="0.08", currency="INR", at=old_at + timedelta(hours=1))
    tiny = service.calculate(actual_cost="0.00127", currency="INR", at=old_at + timedelta(hours=1))
    free = service.calculate(actual_cost="0", currency="INR")
    unpriced = service.calculate(actual_cost=None, currency=None)
    assert paid.status == "calculated" and paid.compute_units == Decimal("8.000000000")
    assert tiny.status == "calculated" and tiny.compute_units == Decimal("0.127000000")
    assert free.status == "free" and free.compute_units == Decimal("0E-9")
    assert unpriced.status == "unpriced" and unpriced.compute_units is None
    assert service.calculate(actual_cost="0.08", currency="INR").compute_units == Decimal("4.000000000")

    event = UsageLedgerService(db).start(user_id=user.id, request_id="historical", feature="chat", operation="chat.generate")
    event.created_at = old_at + timedelta(hours=1)
    event.pricing_status = "priced"
    event.actual_cost = 0.08
    event.cost_currency = "INR"
    converted = service.convert_event(event)
    assert converted.compute_units == Decimal("8.000000000")
    assert event.compute_unit_policy_id == old_policy.id
    # A later policy does not mutate an already calculated historical event.
    assert service.convert_event(event).compute_units == Decimal("8.000000000")

    missing_policy = service.calculate(actual_cost="1", currency="EUR")
    assert missing_policy.status == "policy_missing" and missing_policy.compute_units is None
    db.commit()
    db.close()
