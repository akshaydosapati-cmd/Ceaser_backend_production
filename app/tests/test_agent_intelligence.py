import os
from collections.abc import Generator

os.environ["DATABASE_URL"] = "sqlite://"
os.environ["GEMINI_API_KEY"] = ""

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.agents.registry import AgentRegistry
from app.agents.schemas import AgentContribution
from app.core.database.base import Base
from app.core.database.session import get_db
from app.core.security.dependencies import get_current_user
from app.main import create_app
from app.models.user import User
from app.services.memory_service import MemoryService
from app.services.orchestrator.contribution_merger import ContributionMerger
from app.services.orchestrator.orchestrator import CeaserOrchestrator


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
    user = db.query(User).filter(User.email == "agent-intelligence@example.com").first()
    if not user:
        user = User(email="agent-intelligence@example.com")
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


def current_user_dict() -> dict:
    user = override_current_user()
    return {"id": user.id, "email": user.email}


def contribution_context() -> dict:
    return {
        "message": "Build a healthcare SaaS startup plan",
        "scope": {"id": "user-id", "name": "CEASER", "type": "personal_ai_os"},
        "memories": [{"content": "Clinilocker is a healthcare startup"}],
        "projects": [{"name": "Clinilocker", "status": "planned"}],
        "conversation": [],
        "enabled_agents": [],
        "selected_agents": [],
    }


def test_registry_loads_all_agents() -> None:
    registry = AgentRegistry()

    assert registry.names() == ["Bolt", "Alex", "Friday", "Zeus", "Nova", "Atlas"]
    assert [agent.name for agent in registry.load_many(registry.names())] == registry.names()


def test_all_agents_return_valid_contribution_schema() -> None:
    registry = AgentRegistry()

    for agent in registry.load_many(registry.names()):
        contribution = agent.contribute(contribution_context())
        validated = AgentContribution(**contribution)
        assert validated.agent == agent.name
        assert validated.domain
        assert validated.analysis
        assert validated.recommendations
        assert validated.frameworks_used
        assert 0 <= validated.confidence <= 1


def test_named_agent_contribution_domains() -> None:
    registry = AgentRegistry()
    expected_domains = {
        "Zeus": "Strategy and planning",
        "Nova": "Creative and content",
        "Atlas": "Knowledge and data",
        "Friday": "Productivity and personal execution",
        "Alex": "Research and investigation",
        "Bolt": "Software engineering and application building",
    }

    for name, domain in expected_domains.items():
        contribution = registry.get(name).contribute(contribution_context())  # type: ignore[union-attr]
        assert contribution["domain"] == domain


def test_contribution_merger_removes_duplicates_and_preserves_agents() -> None:
    contributions = [
        {
            "agent": "Zeus",
            "domain": "Business Intelligence",
            "analysis": "Business analysis",
            "recommendations": ["Define ICP", "Build revenue model"],
            "frameworks_used": ["Business Model Canvas"],
            "confidence": 0.9,
        },
        {
            "agent": "Nova",
            "domain": "Research Intelligence",
            "analysis": "Research analysis",
            "recommendations": ["Define ICP", "Map competitors"],
            "frameworks_used": ["Market Research"],
            "confidence": 0.88,
        },
    ]

    merged = ContributionMerger().merge(["Zeus", "Nova"], contributions)

    assert merged["selected_agents"] == ["Zeus", "Nova"]
    assert merged["recommendations"].count("Define ICP") == 1
    assert len(merged["contributions"]) == 2
    assert "CEASER coordinated 2 specialist agents" in merged["summary"]


def test_orchestrator_multi_agent_collaboration() -> None:
    user = current_user_dict()
    db = TestingSessionLocal()
    MemoryService(db).create(user["id"], "project", "Clinilocker is a healthcare startup", {})

    result = CeaserOrchestrator(db).handle_message(user["id"], "Build healthcare SaaS startup plan")
    db.close()

    assert set(result["selected_agents"]) == {"Bolt", "Zeus"}
    assert result["contributions"] == []
    assert result["contribution_summary"]
    assert result["response"]
    assert "CEASER coordinated" not in result["response"]


def test_ceaser_chat_returns_agent_contributions() -> None:
    response = client.post(
        "/ceaser/chat",
        json={"message": "Build healthcare SaaS startup plan"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert set(payload["selected_agents"]) == {"Bolt", "Zeus"}
    assert payload["contribution_summary"]
    assert payload["contributions"] == []
