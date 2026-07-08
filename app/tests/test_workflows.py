import os
from collections.abc import Generator
from uuid import uuid4

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
from app.services.agent_service import AgentService
from app.services.workflows.workflow_router import WorkflowRouter


engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
TestingSessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


def override_db() -> Generator[Session, None, None]:
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


def override_current_user() -> User:
    db = TestingSessionLocal()
    user = db.query(User).filter(User.email == "workflow@example.com").first()
    if not user:
        user = User(email="workflow@example.com")
        db.add(user)
        db.commit()
        db.refresh(user)
    AgentService(db).ensure_default_agents(user.id)
    db.close()
    return user


Base.metadata.create_all(bind=engine)
app = create_app()
app.dependency_overrides[get_db] = override_db
app.dependency_overrides[get_current_user] = override_current_user
client = TestClient(app)


def enabled_agents() -> list[dict]:
    return [{"name": name, "enabled": True, "modules": []} for name in ["Nova", "Zeus", "Bolt", "Friday", "Alex", "Atlas"]]


def test_workflow_router_selects_expected_templates() -> None:
    router = WorkflowRouter()
    assert router.route("Research AI healthcare startups", enabled_agents()).agents == ["Nova"]
    assert router.route("Create a startup strategy", enabled_agents()).agents == ["Nova", "Zeus"]
    assert router.route("Help me launch a healthcare startup", enabled_agents()).agents == ["Nova", "Zeus", "Bolt", "Friday"]
    assert router.route("Help me prepare for my exam", enabled_agents()).agents == ["Nova", "Alex"]
    assert router.route("Design architecture for a SaaS", enabled_agents()).agents == ["Atlas"]


def test_workflow_api_start_history_steps_and_cancel() -> None:
    templates = client.get("/workflows/templates")
    assert templates.status_code == 200
    assert any(item["id"] == "startup" for item in templates.json())

    start = client.post("/workflows/start", json={"message": "Help me launch a healthcare startup"})
    assert start.status_code == 200
    payload = start.json()
    assert payload["workflow_type"] == "startup"
    assert payload["selected_agents"] == ["Nova", "Zeus", "Bolt", "Friday"]
    assert payload["status"] == "completed"
    assert len(payload["steps"]) == 4

    history = client.get("/workflows")
    assert history.status_code == 200
    workflow_id = payload["workflow_id"]
    assert any(item["id"] == workflow_id for item in history.json())

    steps = client.get(f"/workflows/{workflow_id}/steps")
    assert steps.status_code == 200
    assert [step["agent_name"] for step in steps.json()] == ["Nova", "Zeus", "Bolt", "Friday"]

    cancel = client.post(f"/workflows/{workflow_id}/cancel")
    assert cancel.status_code == 200
    assert cancel.json()["status"] == "cancelled"


def test_ceaser_chat_returns_workflow_metadata() -> None:
    conversation = client.post("/conversations", json={"title": f"Workflow Chat {uuid4()}"})
    assert conversation.status_code == 201
    response = client.post(
        "/ceaser/chat",
        json={"message": "I have a startup idea and want a roadmap", "conversation_id": conversation.json()["id"]},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["workflow"]["type"] == "execution"
    assert payload["selected_agents"] == ["Nova", "Zeus", "Bolt"]
    assert "Execution Workflow" in payload["response"]
