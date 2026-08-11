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
from app.engines.research_engine.engine import ResearchEngine
from app.engines.research_engine.page_extractor import PageExtractor
from app.engines.research_engine.schemas import ResearchResult, ResearchSource
from app.engines.research_engine.search_provider import DuckDuckGoSearchProvider
from app.engines.research_engine.source_collector import SourceCollector
from app.services.orchestrator.knowledge_router import KnowledgeRoute, KnowledgeRouter
from app.main import create_app
from app.models.user import User
from app.services.conversation_service import ConversationService
from app.services.llm.gemini_provider import GeminiProvider


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
    user = db.query(User).filter(User.email == "chat-research@example.com").first()
    if not user:
        user = User(email="chat-research@example.com")
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


class FakeSearchProvider:
    def search(self, query: str, limit: int = 6) -> list[dict]:
        return [
            {
                "title": "AI healthcare startups in India 2025",
                "url": "https://example.com/healthcare-ai-india",
                "source": "Example",
                "snippet": "AI healthcare startups in India are growing across clinics and diagnostics.",
            },
            {
                "title": "Duplicate",
                "url": "https://example.com/healthcare-ai-india",
                "source": "Example",
                "snippet": "Duplicate source",
            },
            {
                "title": "General startup report",
                "url": "https://example.com/startups",
                "source": "Example",
                "snippet": "General startup ecosystem context.",
            },
        ][:limit]


class EmptySearchProvider:
    def search(self, query: str, limit: int = 6) -> list[dict]:
        return []


def current_user_dict() -> dict:
    user = override_current_user()
    return {"id": user.id, "email": user.email}


def test_conversation_title_and_message_persistence() -> None:
    conversation = client.post("/conversations", json={}).json()

    response = client.post(
        "/ceaser/chat",
        json={
            "conversation_id": conversation["id"],
            "message": "Build healthcare startup",
        },
    )

    assert response.status_code == 200
    db = TestingSessionLocal()
    restored = ConversationService(db).get(conversation["id"])
    messages = ConversationService(db).list_messages(conversation_id=conversation["id"])
    db.close()

    assert restored.title == "Build Healthcare Startup"
    assert [message.role for message in messages] == ["user", "assistant"]


def test_research_source_collection_deduplicates_and_ranks() -> None:
    sources = SourceCollector(provider=FakeSearchProvider()).collect_sources("AI healthcare startups in India")

    assert len(sources) == 2
    assert sources[0].url == "https://example.com/healthcare-ai-india"
    assert sources[0].score >= sources[1].score


def test_research_engine_builds_citations() -> None:
    result = ResearchEngine(source_collector=SourceCollector(provider=FakeSearchProvider())).research("AI healthcare startups in India")

    assert result.summary
    assert result.key_findings
    assert result.citations[0].url == result.sources[0].url


def test_research_engine_does_not_create_fake_search_source() -> None:
    result = ResearchEngine(source_collector=SourceCollector(provider=EmptySearchProvider())).research("Clinilocker")

    assert result.sources == []
    assert result.citations == []
    assert "No live sources" in result.summary


def test_page_extractor_uses_safe_open_graph_image_only() -> None:
    extractor = PageExtractor()
    html = '<meta property="og:image" content="/images/preview.jpg"><meta name="twitter:image" content="javascript:alert(1)">'

    assert extractor._image_url(html, "https://example.com/article") == "https://example.com/images/preview.jpg"


def test_open_factual_question_uses_live_research() -> None:
    decision = KnowledgeRouter().classify(
        message="What are the war machines India has?",
        has_attached_files=False,
        is_follow_up=False,
    )

    assert decision.route is KnowledgeRoute.RESEARCH


def test_duckduckgo_provider_does_not_fallback_to_search_url(monkeypatch) -> None:
    def raise_error(*args, **kwargs):
        raise RuntimeError("network unavailable")

    monkeypatch.setattr(DuckDuckGoSearchProvider, "_search_html", lambda self, query, limit: [])
    provider = DuckDuckGoSearchProvider()
    monkeypatch.setattr("httpx.Client.get", raise_error)

    assert provider.search("Clinilocker") == []


def test_research_endpoint(monkeypatch) -> None:
    def fake_research(self, query: str) -> ResearchResult:
        return ResearchResult(
            query=query,
            summary="Collected one ranked source.",
            key_findings=["Finding"],
            sources=[
                ResearchSource(
                    title="Source",
                    url="https://example.com",
                    source="Example",
                    snippet="Snippet",
                    score=3,
                )
            ],
            citations=[{"title": "Source", "url": "https://example.com"}],
        )

    monkeypatch.setattr(ResearchEngine, "research", fake_research)
    response = client.post("/research", json={"query": "AI healthcare startups in India"})

    assert response.status_code == 200
    assert response.json()["sources"][0]["url"] == "https://example.com"


def test_gemini_missing_key_falls_back_to_merged_contributions() -> None:
    response = GeminiProvider().generate_response(
        "Build startup",
        {"merged_contributions": {"response": "Merged contribution response"}},
    )

    assert "Executive Summary" in response
    assert "Gemini key is missing" in response
    assert "Merged contribution response" not in response
