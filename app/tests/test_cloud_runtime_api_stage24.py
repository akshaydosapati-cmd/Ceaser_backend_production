from collections.abc import Generator

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.cloud.routes import router
from app.core.database.base import Base
from app.core.database.session import get_db
from app.core.security.dependencies import get_current_user
from app.models.user import User


engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
TestingSession = sessionmaker(bind=engine, autoflush=False, autocommit=False)
current_email = {"value": "owner@example.com"}


def override_db() -> Generator[Session, None, None]:
    with TestingSession() as db:
        yield db


def override_user():
    with TestingSession() as db:
        user = db.query(User).filter(User.email == current_email["value"]).first()
        if not user:
            user = User(email=current_email["value"]); db.add(user); db.commit(); db.refresh(user)
        db.expunge(user)
        return user


app = FastAPI()
app.include_router(router)
app.dependency_overrides[get_db] = override_db
app.dependency_overrides[get_current_user] = override_user
client = TestClient(app)


def setup_function():
    Base.metadata.drop_all(engine); Base.metadata.create_all(engine)
    current_email["value"] = "owner@example.com"


def create_job(**changes):
    body = {"agent_id": "friday", "task_id": "task", "request_id": "request", "capability": "friday.content", "arguments": {"prompt": "Draft a note"}}
    body.update(changes)
    return client.post("/cloud/jobs", json=body)


def test_create_list_get_events_and_cancel_api():
    created = create_job()
    assert created.status_code == 202
    job_id = created.json()["job_id"]
    assert client.get("/cloud/jobs").json()[0]["id"] == job_id
    assert client.get(f"/cloud/jobs/{job_id}").status_code == 200
    assert len(client.get(f"/cloud/jobs/{job_id}/events").json()) == 2
    assert client.post(f"/cloud/jobs/{job_id}/cancel").json()["status"] == "CANCELLED"


def test_cross_user_job_is_hidden():
    job_id = create_job().json()["job_id"]
    current_email["value"] = "other@example.com"
    assert client.get(f"/cloud/jobs/{job_id}").status_code == 404
    assert client.get(f"/cloud/jobs/{job_id}/events").status_code == 404
    assert client.get(f"/cloud/jobs/{job_id}/artifacts").status_code == 404
    assert client.post(f"/cloud/jobs/{job_id}/cancel").status_code == 404


def test_confirmation_api_resumes_exact_job():
    created = create_job(requires_confirmation=True)
    job_id = created.json()["job_id"]
    assert created.json()["status"] == "WAITING_FOR_USER"
    resumed = client.post(f"/cloud/jobs/{job_id}/resume", json={"approved": True, "response": "go ahead"})
    assert resumed.status_code == 200 and resumed.json()["status"] == "QUEUED"


def test_device_only_capability_rejected_by_api():
    response = create_job(capability="desktop.open_application")
    assert response.status_code == 422
