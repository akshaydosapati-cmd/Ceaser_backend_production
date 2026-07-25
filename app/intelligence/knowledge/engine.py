from __future__ import annotations

import asyncio
from time import perf_counter

from sqlalchemy.orm import Session

from app.intelligence.knowledge.models import ContextItem
from app.intelligence.knowledge.repository import KnowledgeRepository
from app.intelligence.orchestrator.models import ProviderPlan, RequestContext, RetrievalPlan
from app.core.database.session import SessionLocal
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
        self.provider_names = {
            "documents",
            "memory",
            "projects",
            "conversation",
            "generated_artifacts",
            "files",
            "calendar",
            "gmail",
            "drive",
            "tasks",
            "classroom",
            "news",
            "weather",
        }

    async def retrieve(self, *, request: RequestContext, plan: RetrievalPlan) -> list[ContextItem]:
        started = perf_counter()
        tasks = [self._retrieve_provider(request=request, provider_plan=provider_plan) for provider_plan in plan.providers]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        items: list[ContextItem] = []
        for result in results:
            if isinstance(result, Exception):
                continue
            items.extend(result)
        providers_run = [provider_plan.provider for provider_plan in plan.providers if provider_plan.provider in self.provider_names]
        self.repository.log_retrieval(
            user_id=request.user_id,
            intent=plan.intent.value,
            provider_names=providers_run,
            chunk_ids=[item.chunk_id or item.id for item in items],
            source_ids=[item.source_id for item in items if item.source_id],
            latency_ms=round((perf_counter() - started) * 1000),
        )
        return items

    async def _retrieve_provider(self, *, request: RequestContext, provider_plan: ProviderPlan) -> list[ContextItem]:
        if provider_plan.provider not in self.provider_names:
            return []

        if provider_plan.provider == "news":
            return await NewsKnowledgeProvider().retrieve(request=request, plan=provider_plan)
        if provider_plan.provider == "weather":
            return await WeatherKnowledgeProvider().retrieve(request=request, plan=provider_plan)

        db = SessionLocal()
        try:
            provider = self._provider_for_db(db, provider_plan.provider)
            if not provider:
                return []
            return await provider.retrieve(request=request, plan=provider_plan)
        finally:
            db.close()

    def _provider_for_db(self, db: Session, provider_name: str):
        if provider_name == "documents":
            return DocumentKnowledgeProvider(db)
        if provider_name == "memory":
            return MemoryProvider(db)
        if provider_name == "projects":
            return ProjectProvider(db)
        if provider_name == "conversation":
            return ConversationProvider(db)
        if provider_name == "generated_artifacts":
            return GeneratedArtifactProvider(db)
        if provider_name == "files":
            return FileMetadataProvider(db)
        if provider_name == "calendar":
            return IntegrationKnowledgeProvider(db, name="calendar", provider_id="google-calendar", kind=ContextKind.CALENDAR_EVENT)
        if provider_name == "gmail":
            return IntegrationKnowledgeProvider(db, name="gmail", provider_id="gmail", kind=ContextKind.EMAIL)
        if provider_name == "drive":
            return IntegrationKnowledgeProvider(db, name="drive", provider_id="google-drive", kind=ContextKind.DRIVE_FILE)
        if provider_name == "tasks":
            return IntegrationKnowledgeProvider(db, name="tasks", provider_id="google-tasks", kind=ContextKind.PROJECT)
        if provider_name == "classroom":
            return IntegrationKnowledgeProvider(db, name="classroom", provider_id="google-classroom", kind=ContextKind.PROJECT)
        return None
