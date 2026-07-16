"""Add CEASER knowledge engine tables.

Revision ID: 20260716_0017
Revises: 20260716_0016
Create Date: 2026-07-16
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision: str = "20260716_0017"
down_revision: str | None = "20260716_0016"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "knowledge_sources",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("organization_id", sa.String(length=36), nullable=True),
        sa.Column("workspace_id", sa.String(length=36), nullable=True),
        sa.Column("project_id", sa.String(length=36), nullable=True),
        sa.Column("subject_id", sa.String(length=36), nullable=True),
        sa.Column("conversation_id", sa.String(length=36), nullable=True),
        sa.Column("title", sa.String(length=500), nullable=False),
        sa.Column("source_type", sa.String(length=80), nullable=False),
        sa.Column("mime_type", sa.String(length=160), nullable=True),
        sa.Column("storage_path", sa.Text(), nullable=True),
        sa.Column("checksum", sa.String(length=128), nullable=True),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("language", sa.String(length=20), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("extra_metadata", sa.JSON(), nullable=False),
        sa.Column("visibility", sa.String(length=40), nullable=False),
        sa.Column("indexed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["conversation_id"], ["conversations.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_knowledge_sources_user_id", "knowledge_sources", ["user_id"])
    op.create_index("ix_knowledge_sources_project_id", "knowledge_sources", ["project_id"])
    op.create_index("ix_knowledge_sources_conversation_id", "knowledge_sources", ["conversation_id"])
    op.create_index("ix_knowledge_sources_source_type", "knowledge_sources", ["source_type"])
    op.create_index("ix_knowledge_sources_status", "knowledge_sources", ["status"])

    op.create_table(
        "knowledge_chunks",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("source_id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("organization_id", sa.String(length=36), nullable=True),
        sa.Column("workspace_id", sa.String(length=36), nullable=True),
        sa.Column("project_id", sa.String(length=36), nullable=True),
        sa.Column("subject_id", sa.String(length=36), nullable=True),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("page_number", sa.Integer(), nullable=True),
        sa.Column("page_end", sa.Integer(), nullable=True),
        sa.Column("slide_number", sa.Integer(), nullable=True),
        sa.Column("sheet_name", sa.String(length=160), nullable=True),
        sa.Column("section_title", sa.String(length=500), nullable=True),
        sa.Column("token_count", sa.Integer(), nullable=False),
        sa.Column("embedding_model", sa.String(length=120), nullable=True),
        sa.Column("embedding_dimension", sa.Integer(), nullable=True),
        sa.Column("embedding", sa.JSON(), nullable=True),
        sa.Column("extra_metadata", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["source_id"], ["knowledge_sources.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_knowledge_chunks_source_id", "knowledge_chunks", ["source_id"])
    op.create_index("ix_knowledge_chunks_user_id", "knowledge_chunks", ["user_id"])
    op.create_index("ix_knowledge_chunks_project_id", "knowledge_chunks", ["project_id"])

    op.create_table(
        "knowledge_retrieval_logs",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("intent", sa.String(length=80), nullable=True),
        sa.Column("provider_names", sa.JSON(), nullable=False),
        sa.Column("retrieved_chunk_ids", sa.JSON(), nullable=False),
        sa.Column("selected_source_ids", sa.JSON(), nullable=False),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(length=40), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_knowledge_retrieval_logs_user_id", "knowledge_retrieval_logs", ["user_id"])

    op.create_table(
        "context_runs",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("conversation_id", sa.String(length=36), nullable=True),
        sa.Column("intent", sa.String(length=80), nullable=False),
        sa.Column("retrieval_plan", sa.JSON(), nullable=False),
        sa.Column("selected_context", sa.JSON(), nullable=False),
        sa.Column("output_format", sa.String(length=80), nullable=True),
        sa.Column("model_provider", sa.String(length=80), nullable=True),
        sa.Column("model_name", sa.String(length=120), nullable=True),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        sa.Column("estimated_cost", sa.Float(), nullable=True),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["conversation_id"], ["conversations.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_context_runs_user_id", "context_runs", ["user_id"])
    op.create_index("ix_context_runs_conversation_id", "context_runs", ["conversation_id"])
    op.create_index("ix_context_runs_intent", "context_runs", ["intent"])


def downgrade() -> None:
    op.drop_index("ix_context_runs_intent", table_name="context_runs")
    op.drop_index("ix_context_runs_conversation_id", table_name="context_runs")
    op.drop_index("ix_context_runs_user_id", table_name="context_runs")
    op.drop_table("context_runs")
    op.drop_index("ix_knowledge_retrieval_logs_user_id", table_name="knowledge_retrieval_logs")
    op.drop_table("knowledge_retrieval_logs")
    op.drop_index("ix_knowledge_chunks_project_id", table_name="knowledge_chunks")
    op.drop_index("ix_knowledge_chunks_user_id", table_name="knowledge_chunks")
    op.drop_index("ix_knowledge_chunks_source_id", table_name="knowledge_chunks")
    op.drop_table("knowledge_chunks")
    op.drop_index("ix_knowledge_sources_status", table_name="knowledge_sources")
    op.drop_index("ix_knowledge_sources_source_type", table_name="knowledge_sources")
    op.drop_index("ix_knowledge_sources_conversation_id", table_name="knowledge_sources")
    op.drop_index("ix_knowledge_sources_project_id", table_name="knowledge_sources")
    op.drop_index("ix_knowledge_sources_user_id", table_name="knowledge_sources")
    op.drop_table("knowledge_sources")
