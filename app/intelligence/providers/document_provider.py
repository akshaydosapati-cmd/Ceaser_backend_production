from __future__ import annotations

from sqlalchemy.orm import Session

from app.intelligence.knowledge.models import ContextItem, ContextKind
from app.intelligence.knowledge.repository import KnowledgeRepository
from app.intelligence.orchestrator.models import ProviderPlan, RequestContext
from app.intelligence.providers.base import KnowledgeProvider
from app.models.knowledge import KnowledgeSource


class DocumentKnowledgeProvider(KnowledgeProvider):
    name = "documents"

    def __init__(self, db: Session) -> None:
        self.repository = KnowledgeRepository(db)

    async def retrieve(self, *, request: RequestContext, plan: ProviderPlan) -> list[ContextItem]:
        chunks = await self.repository.hybrid_search_chunks(
            user_id=request.user_id,
            query=plan.query,
            project_id=plan.filters.get("project_id") or request.project_id,
            source_id=plan.filters.get("source_id") or request.source_id,
            limit=plan.limit,
        )
        source_ids = {chunk.source_id for chunk in chunks}
        sources = {
            source.id: source
            for source in self.repository.db.query(KnowledgeSource).filter(KnowledgeSource.id.in_(source_ids)).all()
        } if source_ids else {}
        return [
            ContextItem(
                id=chunk.id,
                provider=self.name,
                kind=ContextKind.DOCUMENT_CHUNK,
                title=sources.get(chunk.source_id).title if sources.get(chunk.source_id) else chunk.section_title,
                content=chunk.content,
                source_id=chunk.source_id,
                chunk_id=chunk.id,
                relevance_score=0.75,
                permissions=["read"],
                metadata={"section_title": chunk.section_title, "page_number": chunk.page_number},
            )
            for chunk in chunks
        ]
