from datetime import timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.config.settings import settings
from app.core.database.base import Base
from app.models.cloud_runtime import CloudJob
from app.models.mixins import utc_now
from app.models.user import User
from app.schemas.cloud_runtime import CloudJobCreate
from app.services.cloud_runtime import CloudExecutionService, CloudJobError, DurableCloudQueue, PersistentCloudExecutor
from app.services.cloud_runtime.worker import CloudWorker
from app.execution.placement import ExecutionRequest


engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
Session = sessionmaker(bind=engine, autoflush=False, autocommit=False)


@pytest.fixture(autouse=True)
def database(monkeypatch):
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    monkeypatch.setattr(settings, "cloud_jobs_per_user", 3)
    monkeypatch.setattr(settings, "cloud_job_max_attempts", 3)


def users(db):
    one, two = User(email="one@example.com"), User(email="two@example.com")
    db.add_all([one, two]); db.commit(); db.refresh(one); db.refresh(two)
    return one, two


def payload(**updates):
    values = dict(agent_id="friday", task_id="t1", request_id="r1", capability="friday.content", arguments={"prompt": "Draft a launch note"})
    values.update(updates)
    return CloudJobCreate(**values)


def test_job_workspace_events_persist_across_services():
    with Session() as db:
        user, _ = users(db)
        job = CloudExecutionService(db).create(user, payload())
        job_id = job.id
    with Session() as db:
        user = db.query(User).filter_by(email="one@example.com").one()
        service = CloudExecutionService(db)
        loaded = service.owned(user, job_id)
        assert loaded.status == "QUEUED" and loaded.workspace_id
        assert [event.event_type for event in service.events(user, job_id)] == ["cloud.job.created", "cloud.job.queued"]


def test_owner_isolation_for_jobs_events_and_artifacts():
    with Session() as db:
        owner, other = users(db)
        job = CloudExecutionService(db).create(owner, payload())
        service = CloudExecutionService(db)
        assert service.owned(other, job.id) is None
        assert service.events(other, job.id) == [] and service.artifacts(other, job.id) == []


def test_idempotency_returns_same_job():
    with Session() as db:
        user, _ = users(db)
        service = CloudExecutionService(db)
        first = service.create(user, payload(idempotency_key="same"))
        second = service.create(user, payload(idempotency_key="same", request_id="r2"))
        assert first.id == second.id and db.query(CloudJob).count() == 1


def test_database_queue_atomic_lifecycle_and_heartbeat():
    with Session() as db:
        user, _ = users(db)
        job = CloudExecutionService(db).create(user, payload())
        queue = DurableCloudQueue(db, lease_seconds=30)
        claimed = queue.claim_next("w1")
        assert claimed.id == job.id and claimed.status == "RUNNING" and claimed.attempt_count == 1
        assert queue.claim_next("w2") is None
        assert queue.heartbeat(claimed, "w1") is True
        queue.acknowledge(claimed)
        assert claimed.status == "COMPLETED"


def test_stale_lease_recovery_and_bounded_retry():
    with Session() as db:
        user, _ = users(db)
        job = CloudExecutionService(db).create(user, payload())
        queue = DurableCloudQueue(db)
        claimed = queue.claim_next("dead-worker")
        claimed.lease_expires_at = utc_now() - timedelta(seconds=1); db.commit()
        assert queue.release_stale() == 1 and claimed.status == "RETRYING"
        claimed = queue.claim_next("new-worker")
        claimed.attempt_count = claimed.max_attempts; claimed.lease_expires_at = utc_now() - timedelta(seconds=1); db.commit()
        queue.release_stale()
        assert claimed.status == "FAILED"


def test_waiting_confirmation_resume_and_cancel():
    with Session() as db:
        user, _ = users(db)
        service = CloudExecutionService(db)
        job = service.create(user, payload(requires_confirmation=True))
        assert job.status == "WAITING_FOR_USER" and job.pending_action_json
        service.resume(user, job.id, True, "yes")
        assert job.status == "QUEUED" and job.pending_action_json is None
        other = service.create(user, payload(request_id="r2", task_id="t2", requires_confirmation=True))
        service.resume(user, other.id, False)
        assert other.status == "CANCELLED"


def test_cancelled_job_is_not_claimed():
    with Session() as db:
        user, _ = users(db)
        service = CloudExecutionService(db)
        job = service.create(user, payload())
        service.cancel(user, job.id)
        assert DurableCloudQueue(db).claim_next("worker") is None


def test_device_only_and_unknown_capability_rejected():
    with Session() as db:
        user, _ = users(db)
        service = CloudExecutionService(db)
        with pytest.raises(CloudJobError):
            service.create(user, payload(capability="desktop.open_application"))
        with pytest.raises(CloudJobError):
            service.create(user, payload(capability="missing.action"))


def test_concurrency_limit_is_per_user(monkeypatch):
    monkeypatch.setattr(settings, "cloud_jobs_per_user", 1)
    with Session() as db:
        one, two = users(db)
        service = CloudExecutionService(db)
        service.create(one, payload())
        with pytest.raises(CloudJobError):
            service.create(one, payload(request_id="other", task_id="other"))
        assert service.create(two, payload()).user_id == two.id


def test_checkpoint_is_durable_and_redacted():
    with Session() as db:
        user, _ = users(db)
        service = CloudExecutionService(db)
        job = service.create(user, payload(metadata={"api_key": "secret", "safe": "yes"}))
        checkpoint = service.checkpoint(job, 1, {"token": "secret", "stage": "planned"})
        assert checkpoint.state_json == {"stage": "planned"}
        assert job.metadata_json == {"safe": "yes"}


def test_persistent_executor_consumes_stage23_request():
    with Session() as db:
        user, _ = users(db)
        request = ExecutionRequest(
            request_id="placement-r", task_id="placement-t", agent_id="friday", capability="friday.content",
            user_id=user.id, arguments={"prompt": "Draft it"}, metadata={"idempotency_key": "placement"},
        )
        accepted = PersistentCloudExecutor(CloudExecutionService(db), user).submit(request)
        assert accepted["status"] == "QUEUED" and accepted["job_id"]


def test_persistent_executor_rejects_cross_user_request():
    with Session() as db:
        user, _ = users(db)
        request = ExecutionRequest(request_id="r", task_id="t", agent_id="friday", capability="friday.content", user_id="someone-else")
        with pytest.raises(PermissionError):
            PersistentCloudExecutor(CloudExecutionService(db), user).submit(request)


def test_build_worker_fails_closed_without_sandbox(monkeypatch):
    with Session() as db:
        user, _ = users(db)
        job = CloudExecutionService(db).create(user, payload(agent_id="bolt", capability="project.build"))
    monkeypatch.setattr("app.services.cloud_runtime.worker.SessionLocal", Session)
    assert CloudWorker("worker-test").run_once() is True
    with Session() as db:
        loaded = db.get(CloudJob, job.id)
        assert loaded.status == "WAITING_FOR_RESOURCE" and loaded.failure_category == "sandbox_unavailable"


def test_safe_failure_categories_hide_exception_details():
    assert CloudWorker._safe_error(RuntimeError("secret-token-value")) == "Cloud execution failed safely."
