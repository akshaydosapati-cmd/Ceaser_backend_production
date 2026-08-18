from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database.base import Base
from app.models.growth import CreditLedger
from app.models.user import User
from app.services.credit_service import CreditService, InsufficientCreditsError
from app.services.workflows.goal_orchestrator import GoalWorkflowOrchestrator


def database():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, expire_on_commit=False)()


def add_user(db, email):
    user = User(email=email); db.add(user); db.commit(); db.refresh(user); return user


def test_goal_planner_chains_research_into_report_and_presentation():
    plan = GoalWorkflowOrchestrator().plan(user_id="user-1", request="Research current battery technology and prepare a report and presentation.")
    assert [step.capability for step in plan.steps] == ["research.execute", "document.create", "presentation.create"]
    assert plan.steps[1].input_refs == ["research_result"]
    assert plan.steps[2].depends_on == ["step_2"]
    assert not plan.missing_capabilities


def test_email_and_calendar_protected_boundary():
    plan = GoalWorkflowOrchestrator().plan(user_id="user-1", request="Email Rahul and update the calendar meeting.", context={"integrations": ["gmail", "google-calendar"]})
    assert "email.create_draft" in [step.capability for step in plan.steps]
    calendar = next(step for step in plan.steps if step.capability == "calendar.update_event")
    assert calendar.confirmation_required is True


def test_integration_dependent_goal_waits_when_provider_is_missing():
    plan = GoalWorkflowOrchestrator().plan(user_id="user-1", request="Email Rahul about the project review.")
    assert plan.state == "WAITING_FOR_USER"
    assert plan.missing_capabilities == ["email.create_draft"]


def test_wallet_reservation_settlement_release_and_ledger():
    db = database(); user = add_user(db, "wallet@example.com"); service = CreditService(db)
    wallet = service.wallet(user.id); db.commit()
    assert wallet.monthly_balance == 500
    service.reserve(user.id, "request-1", "research", 10)
    service.settle(user.id, "request-1", 7)
    assert service.wallet(user.id).monthly_balance == 493
    service.reserve(user.id, "request-2", "agent_workflow", 20)
    service.release(user.id, "request-2")
    assert service.wallet(user.id).reserved_balance == 0
    assert db.query(CreditLedger).filter(CreditLedger.user_id == user.id).count() >= 2


def test_insufficient_credit_and_zero_cost_local_command():
    db = database(); user = add_user(db, "limits@example.com"); service = CreditService(db)
    service.reserve(user.id, "local", "local_command", 0)
    service.settle(user.id, "local", 0)
    try:
        service.reserve(user.id, "too-big", "research", 999999)
        assert False, "expected insufficient credits"
    except InsufficientCreditsError:
        pass


def test_referral_rewards_both_users_once_and_blocks_self_referral():
    db = database(); referrer = add_user(db, "referrer@example.com"); referred = add_user(db, "referred@example.com")
    service = CreditService(db); code = service.referral_code(referrer.id); db.commit()
    service.apply_referral(referred, code.code)
    assert service.wallet(referrer.id).bonus_balance == 500
    assert service.wallet(referred.id).bonus_balance == 500
    assert service.apply_referral(referred, code.code).status == "rewarded"
    try:
        service.apply_referral(referrer, code.code)
        assert False, "expected self-referral rejection"
    except ValueError:
        pass
