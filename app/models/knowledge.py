from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database.base import Base
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin, utc_now


class KnowledgeSource(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "knowledge_sources"

    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    organization_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    workspace_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    project_id: Mapped[str | None] = mapped_column(ForeignKey("projects.id", ondelete="SET NULL"), index=True, nullable=True)
    subject_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    conversation_id: Mapped[str | None] = mapped_column(ForeignKey("conversations.id", ondelete="SET NULL"), index=True, nullable=True)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    source_type: Mapped[str] = mapped_column(String(80), index=True, nullable=False)
    mime_type: Mapped[str | None] = mapped_column(String(160), nullable=True)
    storage_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    checksum: Mapped[str | None] = mapped_column(String(128), nullable=True)
    status: Mapped[str] = mapped_column(String(40), default="chunked", index=True, nullable=False)
    language: Mapped[str | None] = mapped_column(String(20), nullable=True)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    extra_metadata: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    visibility: Mapped[str] = mapped_column(String(40), default="private", nullable=False)
    indexed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class KnowledgeChunk(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "knowledge_chunks"

    source_id: Mapped[str] = mapped_column(ForeignKey("knowledge_sources.id", ondelete="CASCADE"), index=True, nullable=False)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    organization_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    workspace_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    project_id: Mapped[str | None] = mapped_column(ForeignKey("projects.id", ondelete="SET NULL"), index=True, nullable=True)
    subject_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    page_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    page_end: Mapped[int | None] = mapped_column(Integer, nullable=True)
    slide_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    sheet_name: Mapped[str | None] = mapped_column(String(160), nullable=True)
    section_title: Mapped[str | None] = mapped_column(String(500), nullable=True)
    token_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    embedding_model: Mapped[str | None] = mapped_column(String(120), nullable=True)
    embedding_dimension: Mapped[int | None] = mapped_column(Integer, nullable=True)
    embedding_status: Mapped[str] = mapped_column(String(40), default="pending", index=True, nullable=False)
    embedding: Mapped[list | None] = mapped_column(JSON, nullable=True)
    extra_metadata: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)


class KnowledgeRetrievalLog(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "knowledge_retrieval_logs"

    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    intent: Mapped[str | None] = mapped_column(String(80), nullable=True)
    provider_names: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    retrieved_chunk_ids: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    selected_source_ids: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[str | None] = mapped_column(String(40), nullable=True)


class ContextRun(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "context_runs"

    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    conversation_id: Mapped[str | None] = mapped_column(ForeignKey("conversations.id", ondelete="SET NULL"), index=True, nullable=True)
    intent: Mapped[str] = mapped_column(String(80), index=True, nullable=False)
    retrieval_plan: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    selected_context: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    output_format: Mapped[str | None] = mapped_column(String(80), nullable=True)
    model_provider: Mapped[str | None] = mapped_column(String(80), nullable=True)
    model_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    estimated_cost: Mapped[float | None] = mapped_column(nullable=True)
    status: Mapped[str] = mapped_column(String(40), default="completed", nullable=False)
