from __future__ import annotations

import asyncio

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.config.settings import settings
from app.intelligence.ai.embeddings.registry import embedding_registry
from app.models.knowledge import KnowledgeChunk, KnowledgeSource
from app.models.mixins import utc_now


class KnowledgeEmbeddingService:
    def __init__(self, db: Session) -> None:
        self.db = db

    async def embed_source(self, *, user_id: str, source_id: str) -> int:
        source = self.db.get(KnowledgeSource, source_id)
        if not source or source.user_id != user_id:
            return 0
        chunks = (
            self.db.query(KnowledgeChunk)
            .filter(KnowledgeChunk.user_id == user_id, KnowledgeChunk.source_id == source_id)
            .order_by(KnowledgeChunk.chunk_index.asc())
            .all()
        )
        if not chunks:
            source.status = "empty"
            self.db.flush()
            return 0
        source.status = "embedding"
        self.db.flush()
        try:
            vectors = await embedding_registry.production().embed_documents([chunk.content for chunk in chunks])
            pgvector_enabled = self._pgvector_available()
            for chunk, vector in zip(chunks, vectors, strict=False):
                chunk.embedding = vector
                chunk.embedding_model = settings.openai_embedding_model
                chunk.embedding_dimension = len(vector)
                chunk.embedding_status = "embedded"
                if pgvector_enabled:
                    self._store_pgvector(chunk_id=chunk.id, vector=vector)
            source.indexed_at = utc_now()
            source.status = "ready"
            self.db.flush()
            return len(vectors)
        except Exception:
            for chunk in chunks:
                if chunk.embedding_status != "embedded":
                    chunk.embedding_status = "failed"
            source.status = "embedding_failed"
            self.db.flush()
            raise

    def embed_source_sync(self, *, user_id: str, source_id: str) -> int:
        return asyncio.run(self.embed_source(user_id=user_id, source_id=source_id))

    def _store_pgvector(self, *, chunk_id: str, vector: list[float]) -> None:
        vector_literal = "[" + ",".join(str(float(value)) for value in vector) + "]"
        self.db.execute(
            text("UPDATE knowledge_chunks SET embedding_vector = CAST(:embedding AS vector) WHERE id = :chunk_id"),
            {"embedding": vector_literal, "chunk_id": chunk_id},
        )

    def _pgvector_available(self) -> bool:
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
            return False
