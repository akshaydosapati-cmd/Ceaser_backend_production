from decimal import Decimal

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.models  # noqa: F401
from app.core.database.base import Base
from app.models.commercial import ComputeWalletTransaction
from app.models.user import User
from app.services.compute_wallet_service import ComputeWalletService


engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
Session = sessionmaker(bind=engine)


def test_c4_wallet_accounting_is_idempotent_auditable_and_non_enforcing():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    db = Session()
    user = User(email="wallet-c4@ceaser.local")
    db.add(user)
    db.commit()
    service = ComputeWalletService(db)
    wallet = service.wallet(user.id, included_cu="20")
    assert wallet.available_cu == Decimal("20.000000000")

    service.reserve(user.id, "job-1", "100")
    service.settle(user.id, "job-1", "63.4")
    service.settle(user.id, "job-1", "63.4")
    db.expire_all()
    wallet = service.wallet(user.id)
    assert wallet.reserved_cu == Decimal("0E-9")
    assert wallet.used_cu == Decimal("63.400000000")
    assert wallet.available_cu == Decimal("-43.400000000")  # Accounting only; no denial.
    assert db.query(ComputeWalletTransaction).filter_by(request_id="job-1", transaction_type="settle").count() == 1

    service.reserve(user.id, "free-job", "3")
    service.settle(user.id, "free-job", "0")
    service.settle(user.id, "free-job", "0")
    assert db.query(ComputeWalletTransaction).filter_by(request_id="free-job", transaction_type="settle").count() == 1

    service.reserve(user.id, "job-2", "5")
    service.release(user.id, "job-2")
    service.release(user.id, "job-2")
    service.credit(user.id, "12.5", source="beta", reference_id="launch", metadata={"note": "reward", "token": "hidden"})
    db.expire_all()
    wallet = service.wallet(user.id)
    assert wallet.reserved_cu == Decimal("0E-9") and wallet.bonus_cu == Decimal("12.500000000")
    bonus = db.query(ComputeWalletTransaction).filter_by(transaction_type="bonus").one()
    assert bonus.extra_metadata == {"note": "reward"}
    assert service.record_usage(type("Event", (), {"compute_unit_status": "unpriced", "compute_units": None})()) is None
    db.commit()
    db.close()
