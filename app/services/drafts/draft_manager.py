from __future__ import annotations

from sqlalchemy.orm import Session

from app.engines.research_engine.engine import ResearchEngine
from app.core.config.settings import settings
from app.intelligence.knowledge.embedding_service import KnowledgeEmbeddingService
from app.intelligence.knowledge.repository import KnowledgeRepository
from app.models.draft import Draft
from app.repositories.file_repository import FileRepository
from app.repositories.memory_repository import MemoryRepository
from app.services.drafts.draft_generator import DraftGenerator
from app.services.drafts.draft_router import DraftRouter
from app.services.drafts.draft_storage import DraftStorage


class DraftManager:
    def __init__(self, db: Session):
        self.db = db
        self.storage = DraftStorage(db)

    def create(self, *, user_id: str, prompt: str, draft_type: str | None = None, agent_id: str | None = None, target_app: str = "keep_as_draft", requested_units: int = 8) -> Draft:
        owner_agent, routed_type = DraftRouter().route(prompt, draft_type=draft_type, agent_id=agent_id)
        context = self._context(user_id=user_id, prompt=prompt, draft_type=routed_type)
        content = DraftGenerator().generate(prompt=prompt, draft_type=routed_type, agent_id=owner_agent, target_app=target_app, requested_units=requested_units, context=context)
        draft = self.storage.create(user_id=user_id, agent_id=owner_agent, draft_type=routed_type, prompt=prompt, content=content, target_app=target_app, requested_units=requested_units)
        source = KnowledgeRepository(self.db).ingest_text(
            user_id=user_id,
            title=draft.title,
            content=str(draft.content),
            source_type="draft",
            metadata={"draft_id": draft.id, "draft_type": routed_type, "agent_id": owner_agent, "prompt": prompt},
        )
        if settings.knowledge_auto_embed:
            try:
                KnowledgeEmbeddingService(self.db).embed_source_sync(user_id=user_id, source_id=source.id)
            except Exception:
                pass
        self.db.commit()
        self.db.refresh(draft)
        return draft

    def transition(self, *, draft: Draft, user_id: str, action: str) -> Draft:
        if action == "approved":
            draft.status = "approved"
            draft.progress = 100
        elif action == "archived":
            draft.status = "archived"
        elif action == "regenerated":
            context = self._context(user_id=draft.user_id, prompt=draft.source_prompt, draft_type=draft.draft_type)
            content = DraftGenerator().generate(prompt=draft.source_prompt, draft_type=draft.draft_type, agent_id=draft.agent_id, title=draft.title, target_app=draft.target_app, requested_units=draft.requested_units, context=context)
            draft.content = content.model_dump()
            draft.progress = min(95, draft.progress + 20)
        self.storage.history(draft=draft, user_id=user_id, action=action, detail=f"{action.capitalize()} {draft.title}")
        self.db.commit()
        self.db.refresh(draft)
        return draft

    def _context(self, *, user_id: str, prompt: str, draft_type: str) -> dict:
        memories = [{"type": memory.memory_type, "content": memory.content[:800]} for memory in MemoryRepository(self.db).search(query=prompt, user_id=user_id)[:8]]
        files = [{"name": file.name, "file_type": file.file_type, "content_excerpt": file.extracted_content[:1200]} for file in FileRepository(self.db).list(user_id=user_id)[:5] if file.extracted_content]
        research = {}
        if draft_type in {"research_report", "competitor_analysis", "market_overview", "trend_report"}:
            try:
                research = ResearchEngine().research(prompt).model_dump()
            except Exception:
                research = {}
        return {"memories": memories, "files": files, "research": research}
