import os
from collections.abc import Generator

os.environ["DATABASE_URL"] = "sqlite://"
os.environ["GEMINI_API_KEY"] = ""

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database.base import Base
from app.core.database.session import get_db
from app.core.security.dependencies import get_current_user
from app.main import create_app
from app.models.user import User


engine = create_engine(
    "sqlite://",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


def override_db() -> Generator[Session, None, None]:
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


def override_current_user() -> User:
    db = TestingSessionLocal()
    user = db.query(User).filter(User.email == "automation@example.com").first()
    if not user:
        user = User(email="automation@example.com")
        db.add(user)
        db.commit()
        db.refresh(user)
    db.close()
    return user


Base.metadata.create_all(bind=engine)
app = create_app()
app.dependency_overrides[get_db] = override_db
app.dependency_overrides[get_current_user] = override_current_user
client = TestClient(app)


def test_automation_templates_and_lifecycle() -> None:
    worker_response = client.get("/automations/worker/health")
    assert worker_response.status_code == 200
    assert "enabled" in worker_response.json()

    templates_response = client.get("/automations/templates")
    assert templates_response.status_code == 200
    templates = templates_response.json()
    assert any(template["name"] == "Daily Research Brief" and template["default_agent"] == "nova" for template in templates)
    assert any(template["name"] == "Architecture Review" and template["default_agent"] == "atlas" for template in templates)

    create_response = client.post(
        "/automations",
        json={
            "name": "Daily AI Research Brief",
            "description": "Research AI startup updates every morning.",
            "automation_type": "research",
            "trigger_frequency": "daily",
            "trigger_time": "morning",
            "timezone": "UTC",
            "status": "active",
            "config_json": {"prompt": "Research AI startup updates."},
        },
    )
    assert create_response.status_code == 201
    automation = create_response.json()
    assert automation["assigned_agent"] == "nova"
    assert automation["next_run_at"]

    pause_response = client.post(f"/automations/{automation['id']}/pause")
    assert pause_response.status_code == 200
    assert pause_response.json()["status"] == "paused"
    assert pause_response.json()["next_run_at"] is None

    resume_response = client.post(f"/automations/{automation['id']}/resume")
    assert resume_response.status_code == 200
    assert resume_response.json()["status"] == "active"

    run_response = client.post(f"/automations/{automation['id']}/run-now")
    assert run_response.status_code == 200
    run = run_response.json()
    assert run["status"] in {"completed", "failed"}
    assert run["assigned_agent"] == "nova"

    history_response = client.get(f"/automations/{automation['id']}/runs")
    assert history_response.status_code == 200
    assert len(history_response.json()) == 1

    due_response = client.post("/automations/worker/run-due")
    assert due_response.status_code == 200

    delete_response = client.delete(f"/automations/{automation['id']}")
    assert delete_response.status_code == 204
