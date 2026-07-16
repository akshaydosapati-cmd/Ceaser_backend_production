"""Add semantic RAG vector storage.

Revision ID: 20260716_0018
Revises: 20260716_0017
Create Date: 2026-07-16
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision: str = "20260716_0018"
down_revision: str | None = "20260716_0017"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "knowledge_chunks",
        sa.Column("embedding_status", sa.String(length=40), nullable=False, server_default="pending"),
    )
    op.create_index("ix_knowledge_chunks_embedding_status", "knowledge_chunks", ["embedding_status"])
    op.execute("CREATE INDEX IF NOT EXISTS ix_knowledge_chunks_content_fts ON knowledge_chunks USING gin(to_tsvector('english', coalesce(content, '')))")
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM pg_available_extensions WHERE name = 'vector') THEN
                CREATE EXTENSION IF NOT EXISTS vector;
                EXECUTE 'ALTER TABLE knowledge_chunks ADD COLUMN IF NOT EXISTS embedding_vector vector(1536)';
            END IF;
        END $$;
        """
    )
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'vector')
               AND EXISTS (
                    SELECT 1 FROM information_schema.columns
                    WHERE table_name = 'knowledge_chunks' AND column_name = 'embedding_vector'
               ) THEN
                CREATE INDEX IF NOT EXISTS ix_knowledge_chunks_embedding_vector_hnsw
                ON knowledge_chunks USING hnsw (embedding_vector vector_cosine_ops);
            END IF;
        EXCEPTION WHEN OTHERS THEN
            NULL;
        END $$;
        """
    )
    op.alter_column("knowledge_chunks", "embedding_status", server_default=None)


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_knowledge_chunks_embedding_vector_hnsw")
    op.execute("DROP INDEX IF EXISTS ix_knowledge_chunks_content_fts")
    op.drop_index("ix_knowledge_chunks_embedding_status", table_name="knowledge_chunks")
    op.drop_column("knowledge_chunks", "embedding_status")
    op.execute("ALTER TABLE knowledge_chunks DROP COLUMN IF EXISTS embedding_vector")
