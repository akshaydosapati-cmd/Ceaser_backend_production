import os
from uuid import uuid4
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
from app.services.memory_service import MemoryService
from app.services.orchestrator.agent_selector import AgentSelector
from app.services.orchestrator.memory_capture import MemoryCapture
from app.services.orchestrator.memory_retriever import MemoryRetriever
from app.services.orchestrator.orchestrator import CeaserOrchestrator
from app.services.orchestrator.knowledge_router import KnowledgeRoute
from app.services.orchestrator.user_context_resolver import UserContextResolver


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
    user = db.query(User).filter(User.email == "orchestrator@example.com").first()
    if not user:
        user = User(email="orchestrator@example.com")
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
    db = TestingSessionLocal()
    user = User(email=f"orchestrator-{uuid4()}@example.com")
    db.add(user)
    db.commit()
    db.refresh(user)
    db.close()
    return {"id": user.id, "email": user.email}


def test_user_context_resolver_loads_enabled_agents() -> None:
    user = current_user_dict()
    db = TestingSessionLocal()
    context = UserContextResolver(db).resolve(user["id"])
    db.close()

    assert context["scope"]["type"] == "personal_ai_os"
    assert {agent["name"] for agent in context["enabled_agents"]} == {"Bolt", "Alex", "Friday", "Zeus", "Nova", "Atlas"}


def test_memory_retrieval_ranks_keyword_project_memory() -> None:
    user = current_user_dict()
    db = TestingSessionLocal()
    service = MemoryService(db)
    service.create(user["id"], "conversation", "General onboarding note", {})
    service.create(user["id"], "project", "Healthcare startup Clinilocker launch plan", {})

    ranked = MemoryRetriever(db).retrieve_relevant_memories(user["id"], "Create healthcare startup plan")
    db.close()

    assert ranked[0]["memory_type"] == "project"
    assert "Healthcare startup" in ranked[0]["content"]
    assert ranked[0]["matched_terms"] > 0


def test_memory_retrieval_omits_unrelated_recent_memories() -> None:
    user = current_user_dict()
    db = TestingSessionLocal()
    service = MemoryService(db)
    service.create(user["id"], "project", "Startup name is Clinilocker", {})
    service.create(user["id"], "project", "Co-founder is Ravi", {})

    ranked = MemoryRetriever(db).retrieve_relevant_memories(user["id"], "do a research on healthtech 2026")
    db.close()

    assert ranked == []


def test_agent_selection_uses_routing_config() -> None:
    enabled_agents = [{"name": name, "id": name.lower(), "enabled": True, "modules": []} for name in ["Bolt", "Alex", "Friday", "Zeus", "Nova", "Atlas"]]
    selected = AgentSelector().select_agents("Build SaaS startup and research competitors", enabled_agents)

    assert [agent["name"] for agent in selected] == ["Nova", "Zeus", "Atlas"]


def test_agent_selection_routes_memory_recall_without_atlas() -> None:
    enabled_agents = [{"name": name, "id": name.lower(), "enabled": True, "modules": []} for name in ["Bolt", "Alex", "Friday", "Zeus", "Nova", "Atlas"]]
    selected = AgentSelector().select_agents(
        "What is my startup called? Who is my co-founder? What are we building? Where do we plan to launch?",
        enabled_agents,
    )

    assert [agent["name"] for agent in selected] == ["Zeus"]


def test_agent_selection_routes_web_healthcare_lookup_to_nova() -> None:
    enabled_agents = [{"name": name, "id": name.lower(), "enabled": True, "modules": []} for name in ["Bolt", "Alex", "Friday", "Zeus", "Nova", "Atlas"]]
    selected = AgentSelector().select_agents(
        "Clinilocker is an interoperable digital health record platform. what do you think about this and also you can search it in web using the name Clinilocker.",
        enabled_agents,
    )

    assert [agent["name"] for agent in selected] == ["Nova"]


def test_memory_capture_stores_project_candidate() -> None:
    user = current_user_dict()
    db = TestingSessionLocal()
    captured = MemoryCapture(db).capture(user["id"], "My startup is called Clinilocker")
    memories = MemoryService(db).search("Clinilocker", user["id"])
    db.close()

    assert captured
    assert captured[0]["memory_type"] == "project"
    assert memories[0].extra_metadata["confidence_score"] == 0.9


def test_memory_capture_stores_startup_fact_bundle() -> None:
    user = current_user_dict()
    db = TestingSessionLocal()
    MemoryCapture(db).capture(
        user["id"],
        "My startup is called Clinilocker. My co-founder is Ravi. We are building AI software for healthcare clinics. We plan to launch in Hyderabad.",
    )
    memories = MemoryService(db).search("", user["id"])
    db.close()

    contents = {memory.content for memory in memories}
    assert "Startup name is Clinilocker" in contents
    assert "Co-founder is Ravi" in contents
    assert "Building AI software for healthcare clinics" in contents
    assert "Launch location is Hyderabad" in contents


def test_orchestrator_returns_brain_payload() -> None:
    user = current_user_dict()
    db = TestingSessionLocal()
    MemoryService(db).create(user["id"], "project", "Clinilocker is a healthcare startup", {})

    result = CeaserOrchestrator(db).handle_message(user["id"], "Create a healthcare startup plan")
    db.close()

    assert result["scope"] == "personal_ai_os"
    assert "Zeus" in result["selected_agents"]
    assert result["selected_agents"] == ["Zeus"]
    assert result["memories_used"]
    assert result["context_summary"]["memory_count"] >= 1
    assert result["response"]


def test_orchestrator_extracts_named_research_query(monkeypatch) -> None:
    user = current_user_dict()
    captured_queries = []

    def fake_research(self, query: str):
        captured_queries.append(query)
        from app.engines.research_engine.schemas import ResearchResult

        return ResearchResult(query=query, summary="No live sources were found.", key_findings=[], sources=[], citations=[])

    monkeypatch.setattr("app.engines.research_engine.engine.ResearchEngine.research", fake_research)
    db = TestingSessionLocal()
    result = CeaserOrchestrator(db).handle_message(
        user["id"],
        "do some research on Clinilocker and give me the resources you did.",
    )
    db.close()

    assert captured_queries == ["Clinilocker"]
    assert result["selected_agents"] == ["Alex"]
    assert result["research"]["query"] == "Clinilocker"


def test_orchestrator_extracts_generic_research_topics() -> None:
    orchestrator = CeaserOrchestrator.__new__(CeaserOrchestrator)

    assert orchestrator._research_query("do a research on healthtech 2026 and then give me the resources.") == "healthtech 2026"
    assert orchestrator._research_query("search the web for AI healthcare startups in India and give sources") == "AI healthcare startups in India"
    assert orchestrator._research_query("look up federated data architectures in healthcare") == "federated data architectures in healthcare"


def test_live_research_runs_only_without_internal_context() -> None:
    assert CeaserOrchestrator._should_run_live_research(route=KnowledgeRoute.GENERAL, has_internal_context=False) is True
    assert CeaserOrchestrator._should_run_live_research(route=KnowledgeRoute.GENERAL, has_internal_context=True) is False
    assert CeaserOrchestrator._should_run_live_research(route=KnowledgeRoute.FOLLOW_UP, has_internal_context=False) is False


def test_generic_memory_match_does_not_block_live_research() -> None:
    assert CeaserOrchestrator._has_relevant_internal_context(
        message="Explain the main characters of Mahabharata",
        knowledge_context={"evidence": ""},
        memories=[{"content": "Explain this in simple words next time."}],
    ) is False


def test_relevant_user_memory_still_blocks_live_research() -> None:
    assert CeaserOrchestrator._has_relevant_internal_context(
        message="Summarize my CliniLocker project",
        knowledge_context={"evidence": ""},
        memories=[{"content": "CliniLocker project is a healthcare records platform."}],
    ) is True


def test_filler_prefixed_expand_request_continues_active_topic() -> None:
    orchestrator = CeaserOrchestrator.__new__(CeaserOrchestrator)

    resolution = orchestrator._resolve_conversation_turn("fine explain more", "Recent Assam floods")

    assert resolution["follow_up_detected"] is True
    assert resolution["new_topic"] is False
    assert resolution["active_topic"] == "Recent Assam floods"
    assert resolution["intent"] == "expand"


def test_follow_up_uses_previous_exchange_when_topic_extraction_is_empty(monkeypatch) -> None:
    orchestrator = CeaserOrchestrator.__new__(CeaserOrchestrator)
    monkeypatch.setattr(orchestrator, "_topic_from_previous_assistant", lambda _content: None)
    monkeypatch.setattr(orchestrator, "_topic_from_previous_user", lambda _content: None)
    context = {
        "previous_research": None,
        "active_topic": None,
        "active_subtopic": None,
        "inferred_topic": None,
        "latest_user_message": {"id": "user-1", "content": "Tell me about a subject."},
        "latest_assistant_message": {"id": "assistant-1", "content": "A plain answer without a Markdown heading."},
        "named_entities": [],
        "summary": None,
    }

    trace = orchestrator._follow_up_trace(message="explain more", conversation_context=context, parent_message_id=None)

    assert trace["follow_up_detected"] is True
    assert trace["active_topic"] is None
    assert trace["context_source"] == ["previous_user_message", "previous_assistant_answer"]


def test_ceaser_chat_endpoint() -> None:
    response = client.post(
        "/ceaser/chat",
        json={"message": "Build startup plan and research competitors"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["scope"] == "personal_ai_os"
    assert "Zeus" in payload["selected_agents"]
    assert "Alex" in payload["selected_agents"]
    assert "response" in payload
