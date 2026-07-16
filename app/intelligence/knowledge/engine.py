from __future__ import annotations

from time import perf_counter

from sqlalchemy.orm import Session

from app.intelligence.knowledge.models import ContextItem
from app.intelligence.knowledge.repository import KnowledgeRepository
from app.intelligence.orchestrator.models import RequestContext, RetrievalPlan
from app.intelligence.providers.document_provider import DocumentKnowledgeProvider
from app.intelligence.providers.local_providers import (
    ConversationProvider,
    FileMetadataProvider,
    GeneratedArtifactProvider,
    MemoryProvider,
    ProjectProvider,
)
from app.intelligence.providers.integration_providers import IntegrationKnowledgeProvider
from app.intelligence.knowledge.models import ContextKind
from app.intelligence.providers.live_providers import NewsKnowledgeProvider, WeatherKnowledgeProvider


class KnowledgeEngine:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.repository = KnowledgeRepository(db)
        self.providers = {
            "documents": DocumentKnowledgeProvider(db),
            "memory": MemoryProvider(db),
            "projects": ProjectProvider(db),
            "conversation": ConversationProvider(db),
            "generated_artifacts": GeneratedArtifactProvider(db),
            "files": FileMetadataProvider(db),
            "calendar": IntegrationKnowledgeProvider(db, name="calendar", provider_id="google-calendar", kind=ContextKind.CALENDAR_EVENT),
            "gmail": IntegrationKnowledgeProvider(db, name="gmail", provider_id="gmail", kind=ContextKind.EMAIL),
            "drive": IntegrationKnowledgeProvider(db, name="drive", provider_id="google-drive", kind=ContextKind.DRIVE_FILE),
            "tasks": IntegrationKnowledgeProvider(db, name="tasks", provider_id="google-tasks", kind=ContextKind.PROJECT),
            "classroom": IntegrationKnowledgeProvider(db, name="classroom", provider_id="google-classroom", kind=ContextKind.PROJECT),
            "news": NewsKnowledgeProvider(),
            "weather": WeatherKnowledgeProvider(),
        }

    async def retrieve(self, *, request: RequestContext, plan: RetrievalPlan) -> list[ContextItem]:
        started = perf_counter()
        items: list[ContextItem] = []
        providers_run: list[str] = []
        for provider_plan in plan.providers:
            provider = self.providers.get(provider_plan.provider)
            if not provider:
                continue
            providers_run.append(provider_plan.provider)
            items.extend(await provider.retrieve(request=request, plan=provider_plan))
        self.repository.log_retrieval(
            user_id=request.user_id,
            intent=plan.intent.value,
            provider_names=providers_run,
            chunk_ids=[item.chunk_id or item.id for item in items],
            source_ids=[item.source_id for item in items if item.source_id],
            latency_ms=round((perf_counter() - started) * 1000),
        )
        return items
