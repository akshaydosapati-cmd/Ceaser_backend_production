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
        source_id = plan.filters.get("source_id") or request.source_id
        trace = request.metadata.setdefault("rag_trace", {})
        if source_id and self._is_broad_summary_query(plan.query):
            chunks = self.repository.load_source_chunks(
                user_id=request.user_id,
                source_id=source_id,
                limit=min(plan.limit, 6),
                trace=trace,
            )
        else:
            chunks = await self.repository.hybrid_search_chunks(
                user_id=request.user_id,
                query=plan.query,
                project_id=plan.filters.get("project_id") or request.project_id,
                source_id=source_id,
                limit=plan.limit,
                trace=trace,
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

    def _is_broad_summary_query(self, query: str) -> bool:
        normalized = query.lower().strip()
        broad_terms = (
            "summarize the uploaded document",
            "summarize the uploaded file",
            "summarize this document",
            "summarize this file",
            "summarize the document",
            "summarize the file",
            "summary of the document",
            "summary of this file",
        )
        return any(term in normalized for term in broad_terms)
