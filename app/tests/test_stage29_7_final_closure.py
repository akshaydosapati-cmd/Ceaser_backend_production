from datetime import timedelta

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database.base import Base
from app.models.integration import Integration
from app.models.growth import CreditLedger, CreditProduct, CreditPurchase
from app.models.user import User
from app.services.credit_service import CreditService, InsufficientCreditsError
from app.services.billing_service import RazorpayGateway
from app.services.workflows.capability_executor import CapabilityOutcome, WorkflowCapabilityExecutor
from app.services.workflows.goal_orchestrator import GoalWorkflowOrchestrator
from app.services.workflows.workflow_executor import WorkflowExecutor
from app.services.workflows.workflow_manager import WorkflowManager
from app.services.integrations.gmail_provider import GmailProvider
from app.services.integrations.google_calendar_provider import GoogleCalendarProvider
from app.models.mixins import utc_now
from app.services.workflows.schemas import GoalWorkflowPlan, GoalWorkflowStep, UserGoal


def database():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, expire_on_commit=False)()


def user(db, email="closure@example.com"):
    row = User(email=email)
    db.add(row); db.commit(); db.refresh(row)
    return row


def test_multi_output_dag_shares_one_research_result():
    plan = GoalWorkflowOrchestrator().plan(user_id="u", request="Research safe battery technology and create a report and presentation")
    assert [step.capability for step in plan.steps] == ["research.execute", "document.create", "presentation.create"]
    assert plan.steps[1].depends_on == plan.steps[2].depends_on == ["step_1"]
    assert plan.steps[1].input_refs == plan.steps[2].input_refs == ["research_result"]


def test_production_runner_passes_structured_outputs_without_regeneration(monkeypatch):
    db = database(); owner = user(db)
    plan = GoalWorkflowOrchestrator().plan(user_id=owner.id, request="Research safe battery technology and create a report and presentation")
    run = WorkflowManager(db).create_goal_plan(plan)
    seen = []
    def execute(_self, capability, **kwargs):
        seen.append((capability, kwargs["inputs"]))
        if capability == "research.execute":
            return CapabilityOutcome("COMPLETED", {"summary": "grounded", "sources": [{"url": "https://example.com"}]}, "Research completed.", True)
        return CapabilityOutcome("COMPLETED", {"file_id": capability, "sources": kwargs["inputs"]["research_result"]["sources"]}, "Artifact created.", True)
    monkeypatch.setattr(WorkflowCapabilityExecutor, "execute", execute)
    result = WorkflowExecutor(db).execute_goal_plan(run=run, plan=plan)
    assert result["run"].status == "completed"
    assert seen[1][1]["research_result"] is seen[2][1]["research_result"]
    assert result["outputs"]["document_artifact"]["sources"] == [{"url": "https://example.com"}]


def test_missing_gmail_waits_and_does_not_claim_success():
    db = database(); owner = user(db)
    plan = GoalWorkflowOrchestrator().plan(user_id=owner.id, request="Draft an email to test@example.com about the project")
    run = WorkflowManager(db).create_goal_plan(plan)
    result = WorkflowExecutor(db).execute_goal_plan(run=run, plan=plan)
    assert result["run"].status == "waiting_for_user"
    assert run.steps[-1].status == "waiting_for_user"
    assert run.steps[-1].metadata_json["availability"] == "REQUIRES_INTEGRATION"


def test_confirmation_resume_reuses_exact_draft(monkeypatch):
    db = database(); owner = user(db)
    integration = Integration(user_id=owner.id, provider="gmail", status="connected")
    integration.access_token = "test-token"
    db.add(integration); db.commit()
    plan = GoalWorkflowOrchestrator().plan(user_id=owner.id, request="Send an email to test@example.com about the project")
    run = WorkflowManager(db).create_goal_plan(plan)
    calls = []
    def execute(_self, capability, **kwargs):
        calls.append((capability, kwargs["inputs"], kwargs["confirmed"]))
        if capability == "email.create_draft":
            return CapabilityOutcome("COMPLETED", {"id": "draft-1", "to": "test@example.com", "subject": "Project", "body": "Ready"}, "Draft ready.", True)
        return CapabilityOutcome("COMPLETED", {"message_id": "sent-1", "draft_id": kwargs["inputs"]["email_draft"]["id"]}, "Email sent.", True)
    monkeypatch.setattr(WorkflowCapabilityExecutor, "execute", execute)
    first = WorkflowExecutor(db).execute_goal_plan(run=run, plan=plan)
    assert first["run"].status == "waiting_for_user"
    second = WorkflowExecutor(db).execute_goal_plan(run=run, plan=plan, confirmed_capability="email.send")
    assert second["run"].status == "completed"
    assert calls[-1][1]["email_draft"]["body"] == "Ready"
    assert [item[0] for item in calls].count("email.create_draft") == 1


def test_capability_availability_is_truthful():
    db = database(); owner = user(db)
    service = WorkflowCapabilityExecutor(db)
    assert service.availability("email.create_draft", owner.id) == "REQUIRES_INTEGRATION"
    assert service.availability("office.fake_edit", owner.id) == "UNAVAILABLE"


def test_missing_capability_replan_is_bounded_and_preserves_outputs():
    db = database(); owner = user(db, "replan@example.com")
    plan = GoalWorkflowPlan(
        workflow_id="replan-workflow",
        goal=UserGoal(goal_id="replan-goal", user_id=owner.id, original_request="Use an unavailable capability", inferred_outcome="workflow"),
        steps=[GoalWorkflowStep(step_id="step_1", capability="office.fake_edit", responsible_agent="Bolt", execution_target="cloud", output_name="result", verification_rule="verified result required")],
    )
    run = WorkflowManager(db).create_goal_plan(plan)
    result = WorkflowExecutor(db).execute_goal_plan(run=run, plan=plan)
    assert result["run"].status == "failed"
    assert result["run"].metadata_json["replan_attempts"] == ["office.fake_edit"]
    assert result["run"].metadata_json["replan_exhausted"] is True


def test_native_gmail_and_calendar_write_contracts(monkeypatch):
    db = database(); owner = user(db, "writes@example.com")
    gmail = Integration(user_id=owner.id, provider="gmail", status="connected")
    calendar = Integration(user_id=owner.id, provider="google-calendar", status="connected")
    gmail.access_token = calendar.access_token = "safe-test-token"
    db.add_all([gmail, calendar]); db.commit()
    requests = []
    def request(_self, _integration, method, url, *, payload=None):
        requests.append((method, url, payload))
        return {"id": "verified-id", "status": "confirmed", "htmlLink": "https://calendar.test/event"}
    monkeypatch.setattr(GmailProvider, "google_request", request)
    monkeypatch.setattr(GoogleCalendarProvider, "google_request", request)
    service = WorkflowCapabilityExecutor(db)
    draft = service.execute("email.create_draft", user_id=owner.id, request="Email test@example.com", inputs={})
    event = service.execute("calendar.create_event", user_id=owner.id, request="Planning", inputs={"calendar_event": {"start": {"dateTime": "2026-08-20T10:00:00+05:30"}, "end": {"dateTime": "2026-08-20T11:00:00+05:30"}}})
    assert draft.verified and draft.output["draft_id"] == "verified-id"
    assert event.verified and event.output["id"] == "verified-id"
    assert requests[0][0] == "POST" and requests[0][1].endswith("/drafts")
    assert requests[1][0] == "POST" and requests[1][1].endswith("/events")


def test_referral_attribution_waits_for_verification_and_rewards_once():
    db = database(); referrer = user(db, "referrer-closure@example.com"); referred = user(db, "referred-closure@example.com")
    service = CreditService(db); code = service.referral_code(referrer.id); db.commit()
    captured = service.apply_referral(referred, code.code, verified=False)
    assert captured.status == "pending"
    assert service.wallet(referrer.id).bonus_balance == 0
    service.finalize_referral(referred)
    service.finalize_referral(referred)
    assert service.wallet(referrer.id).bonus_balance == 500
    assert service.wallet(referred.id).bonus_balance == 500
    assert db.query(CreditLedger).filter(CreditLedger.transaction_type == "referral").count() == 2


def test_existing_account_cannot_claim_new_signup_referral():
    db = database(); referrer = user(db, "old-referrer@example.com"); referred = user(db, "old-account@example.com")
    referred.created_at = utc_now() - timedelta(days=2)
    code = CreditService(db).referral_code(referrer.id); db.commit()
    try:
        CreditService(db).apply_referral(referred, code.code)
        assert False, "expected existing-account rejection"
    except ValueError as exc:
        assert "new accounts" in str(exc)


def test_credit_request_retry_is_idempotent_and_cannot_overspend():
    db = database(); owner = user(db, "metering@example.com"); service = CreditService(db)
    first = service.reserve(owner.id, "same-request", "agent_workflow", 80)
    second = service.reserve(owner.id, "same-request", "agent_workflow", 80)
    assert first.id == second.id
    wallet = service.wallet(owner.id)
    assert wallet.reserved_balance == 80
    try:
        service.reserve(owner.id, "other-request", "agent_workflow", 450)
        assert False, "expected atomic insufficient-credit rejection"
    except InsufficientCreditsError:
        pass
    assert service.wallet(owner.id).reserved_balance == 80


def test_razorpay_purchase_converges_once_and_rejects_cross_user(monkeypatch):
    db = database(); owner = user(db, "buyer@example.com"); attacker = user(db, "attacker@example.com")
    product = CreditProduct(code="PACK_TEST", name="Test Pack", credits=100, amount_inr=99, active=True, plan_eligibility={"plans": ["FREE"]}, display_order=1)
    db.add(product); db.flush()
    purchase = CreditPurchase(user_id=owner.id, credit_product_id=product.id, razorpay_order_id="order-1", amount=9900, credits=100, status="created")
    db.add(purchase); db.commit()
    monkeypatch.setattr(RazorpayGateway, "verify_payment_signature", lambda *args, **kwargs: True)
    monkeypatch.setattr(RazorpayGateway, "fetch_payment", lambda *args, **kwargs: {"id": "pay-1", "order_id": "order-1", "status": "captured", "amount": 9900})
    service = CreditService(db)
    try:
        service.verify_purchase(attacker.id, "order-1", "pay-1", "sig")
        assert False, "expected cross-user rejection"
    except ValueError:
        pass
    service.verify_purchase(owner.id, "order-1", "pay-1", "sig")
    service.apply_payment_webhook({"id": "pay-1", "order_id": "order-1", "amount": 9900}, "payment.captured")
    db.commit()
    assert service.wallet(owner.id).purchased_balance == 100
    assert db.query(CreditLedger).filter(CreditLedger.transaction_type == "purchase").count() == 1
