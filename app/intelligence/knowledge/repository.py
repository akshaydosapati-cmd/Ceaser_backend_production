from __future__ import annotations

from time import perf_counter

from sqlalchemy import or_, text
from sqlalchemy.orm import Session

from app.core.config.settings import settings
from app.intelligence.ai.ai_provider_service import ai_provider_service
from app.intelligence.knowledge.chunker import text_chunker
from app.models.knowledge import ContextRun, KnowledgeChunk, KnowledgeRetrievalLog, KnowledgeSource
from app.models.mixins import utc_now


class KnowledgeRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def list_sources(self, *, user_id: str, limit: int = 50) -> list[KnowledgeSource]:
        return (
            self.db.query(KnowledgeSource)
            .filter(KnowledgeSource.user_id == user_id, KnowledgeSource.deleted_at.is_(None))
            .order_by(KnowledgeSource.created_at.desc())
            .limit(limit)
            .all()
        )

    def ingest_text(
        self,
        *,
        user_id: str,
        title: str,
        content: str,
        source_type: str,
        project_id: str | None = None,
        conversation_id: str | None = None,
        metadata: dict | None = None,
    ) -> KnowledgeSource:
        source = KnowledgeSource(
            user_id=user_id,
            title=title,
            source_type=source_type,
            status="chunking",
            project_id=project_id,
            conversation_id=conversation_id,
            extra_metadata=metadata or {},
            indexed_at=utc_now(),
        )
        self.db.add(source)
        self.db.flush()
        chunks = text_chunker.chunk(content)
        for index, chunk in enumerate(chunks):
            self.db.add(
                KnowledgeChunk(
                    source_id=source.id,
                    user_id=user_id,
                    project_id=project_id,
                    chunk_index=index,
                    content=chunk,
                    token_count=max(1, len(chunk) // 4),
                    embedding_model=settings.openai_embedding_model,
                    embedding_dimension=settings.openai_embedding_dimension,
                    embedding_status="pending",
                    extra_metadata={},
                )
            )
        source.status = "chunked" if chunks else "empty"
        return source

    def pgvector_available(self) -> bool:
        if not settings.knowledge_use_pgvector:
            return False
        try:
            return bool(
                self.db.execute(
                    text(
                        """
                        SELECT EXISTS (
                            SELECT 1 FROM information_schema.columns
                            WHERE table_name = 'knowledge_chunks'
                              AND column_name = 'embedding_vector'
                        )
                        """
                    )
                ).scalar()
            )
        except Exception:
            self.db.rollback()
            return False

    def _base_chunk_query(self, *, user_id: str, project_id: str | None = None, source_id: str | None = None):
        db_query = (
            self.db.query(KnowledgeChunk)
            .join(KnowledgeSource, KnowledgeSource.id == KnowledgeChunk.source_id)
            .filter(
                KnowledgeChunk.user_id == user_id,
                KnowledgeSource.user_id == user_id,
                KnowledgeSource.deleted_at.is_(None),
                KnowledgeSource.status != "deleted",
            )
        )
        if project_id:
            db_query = db_query.filter(KnowledgeChunk.project_id == project_id)
        if source_id:
            db_query = db_query.filter(KnowledgeChunk.source_id == source_id)
        return db_query

    def keyword_search_chunks(
        self,
        *,
        user_id: str,
        query: str,
        project_id: str | None = None,
        source_id: str | None = None,
        limit: int = 8,
    ) -> list[KnowledgeChunk]:
        terms = [term.strip() for term in query.split() if len(term.strip()) > 2]
        db_query = self._base_chunk_query(user_id=user_id, project_id=project_id, source_id=source_id)
        if terms:
            filters = []
            for term in terms[:8]:
                like = f"%{term}%"
                filters.extend([KnowledgeChunk.content.ilike(like), KnowledgeSource.title.ilike(like)])
            db_query = db_query.filter(or_(*filters))
        return db_query.order_by(KnowledgeChunk.created_at.desc()).limit(limit).all()

    def search_chunks(
        self,
        *,
        user_id: str,
        query: str,
        project_id: str | None = None,
        source_id: str | None = None,
        limit: int = 8,
    ) -> list[KnowledgeChunk]:
        return self.keyword_search_chunks(
            user_id=user_id,
            query=query,
            project_id=project_id,
            source_id=source_id,
            limit=limit,
        )

    async def hybrid_search_chunks(
        self,
        *,
        user_id: str,
        query: str,
        project_id: str | None = None,
        source_id: str | None = None,
        limit: int = 8,
    ) -> list[KnowledgeChunk]:
        keyword = self.keyword_search_chunks(
            user_id=user_id,
            query=query,
            project_id=project_id,
            source_id=source_id,
            limit=limit,
        )
        vector = await self.vector_search_chunks(
            user_id=user_id,
            query=query,
            project_id=project_id,
            source_id=source_id,
            limit=limit,
        )
        return self._rank_fuse([keyword, vector], limit=limit)

    async def vector_search_chunks(
        self,
        *,
        user_id: str,
        query: str,
        project_id: str | None = None,
        source_id: str | None = None,
        limit: int = 8,
    ) -> list[KnowledgeChunk]:
        if not self.pgvector_available():
            return []
        try:
            embedding = await ai_provider_service.embeddings.production().embed_query(query)
            if not embedding:
                return []
            vector_literal = "[" + ",".join(str(float(value)) for value in embedding) + "]"
            filters = [
                "kc.user_id = :user_id",
                "ks.user_id = :user_id",
                "ks.deleted_at IS NULL",
                "ks.status <> 'deleted'",
                "kc.embedding_vector IS NOT NULL",
            ]
            params: dict[str, object] = {"user_id": user_id, "embedding": vector_literal, "limit": limit}
            if project_id:
                filters.append("kc.project_id = :project_id")
                params["project_id"] = project_id
            if source_id:
                filters.append("kc.source_id = :source_id")
                params["source_id"] = source_id
            rows = self.db.execute(
                text(
                    f"""
                    SELECT kc.id
                    FROM knowledge_chunks kc
                    JOIN knowledge_sources ks ON ks.id = kc.source_id
                    WHERE {' AND '.join(filters)}
                    ORDER BY kc.embedding_vector <=> CAST(:embedding AS vector)
                    LIMIT :limit
                    """
                ),
                params,
            ).all()
            ids = [row[0] for row in rows]
            if not ids:
                return []
            chunks = self.db.query(KnowledgeChunk).filter(KnowledgeChunk.id.in_(ids)).all()
            by_id = {chunk.id: chunk for chunk in chunks}
            return [by_id[item_id] for item_id in ids if item_id in by_id]
        except Exception:
            self.db.rollback()
            return []

    def _rank_fuse(self, ranked_lists: list[list[KnowledgeChunk]], *, limit: int) -> list[KnowledgeChunk]:
        scores: dict[str, float] = {}
        chunks: dict[str, KnowledgeChunk] = {}
        for ranked in ranked_lists:
            for rank, chunk in enumerate(ranked):
                chunks[chunk.id] = chunk
                scores[chunk.id] = scores.get(chunk.id, 0.0) + (1.0 / (60 + rank + 1))
        return [chunks[item_id] for item_id, _ in sorted(scores.items(), key=lambda item: item[1], reverse=True)[:limit]]

    def log_retrieval(
        self,
        *,
        user_id: str,
        intent: str,
        provider_names: list[str],
        chunk_ids: list[str],
        source_ids: list[str],
        latency_ms: int,
        status: str = "completed",
    ) -> KnowledgeRetrievalLog:
        log = KnowledgeRetrievalLog(
            user_id=user_id,
            intent=intent,
            provider_names=provider_names,
            retrieved_chunk_ids=chunk_ids,
            selected_source_ids=source_ids,
            latency_ms=latency_ms,
            status=status,
        )
        self.db.add(log)
        return log

    def record_context_run(
        self,
        *,
        user_id: str,
        conversation_id: str | None,
        intent: str,
        retrieval_plan: dict,
        selected_context: list[dict],
        output_format: str,
        model_provider: str | None = None,
        model_name: str | None = None,
        started: float | None = None,
        status: str = "completed",
    ) -> ContextRun:
        latency_ms = round((perf_counter() - started) * 1000) if started else None
        run = ContextRun(
            user_id=user_id,
            conversation_id=conversation_id,
            intent=intent,
            retrieval_plan=retrieval_plan,
            selected_context=selected_context,
            output_format=output_format,
            model_provider=model_provider,
            model_name=model_name,
            latency_ms=latency_ms,
            status=status,
        )
        self.db.add(run)
        return run
