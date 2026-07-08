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
    user = db.query(User).filter(User.email == "test@example.com").first()
    if not user:
        user = User(email="test@example.com")
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


def test_user_scoped_agent_provisioning() -> None:
    agents_response = client.get("/agents")
    assert agents_response.status_code == 200
    agents = agents_response.json()
    assert {agent["name"] for agent in agents} == {"Bolt", "Alex", "Friday", "Zeus", "Nova", "Atlas"}
    assert all(agent["modules"] for agent in agents)

    atlas = next(agent for agent in agents if agent["name"] == "Atlas")
    disabled = client.post(f"/agents/{atlas['id']}/disable")
    assert disabled.status_code == 200
    assert disabled.json()["enabled"] is False

    enabled = client.post(f"/agents/{atlas['id']}/enable")
    assert enabled.status_code == 200
    assert enabled.json()["enabled"] is True


def test_conversation_message_memory_project_and_file_persistence() -> None:
    project_response = client.post(
        "/projects",
        json={
            "name": "Launch Plan",
            "description": "Sprint foundation",
            "status": "planned",
        },
    )
    assert project_response.status_code == 201
    project = project_response.json()

    file_response = client.post(
        "/files",
        json={
            "project_id": project["id"],
            "name": "brief.docx",
            "file_type": "docx",
            "storage_path": "users/brief.docx",
        },
    )
    assert file_response.status_code == 201

    conversation_response = client.post("/conversations", json={"title": "Kickoff"})
    assert conversation_response.status_code == 201
    conversation = conversation_response.json()

    message_response = client.post(
        "/messages",
        json={"conversation_id": conversation["id"], "role": "user", "content": "Remember the launch plan."},
    )
    assert message_response.status_code == 201

    memory_response = client.post(
        "/memories",
        json={
            "memory_type": "project",
            "content": "Launch plan is the current priority.",
            "metadata": {"project_id": project["id"]},
        },
    )
    assert memory_response.status_code == 201

    search_response = client.post("/memories/search", json={"query": "Launch"})
    assert search_response.status_code == 200
    assert len(search_response.json()) >= 1
