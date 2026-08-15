from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Index, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database.base import Base
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin


class CloudJob(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "cloud_jobs"
    __table_args__ = (
        UniqueConstraint("user_id", "idempotency_key", name="uq_cloud_jobs_user_idempotency"),
        Index("ix_cloud_jobs_queue", "status", "available_at", "created_at"),
    )

    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    agent_id: Mapped[str] = mapped_column(String(80), index=True)
    task_id: Mapped[str] = mapped_column(String(120), index=True)
    request_id: Mapped[str] = mapped_column(String(120), index=True)
    idempotency_key: Mapped[str | None] = mapped_column(String(160), nullable=True)
    status: Mapped[str] = mapped_column(String(40), default="QUEUED", index=True)
    execution_target: Mapped[str] = mapped_column(String(20), default="CLOUD")
    workspace_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    parent_job_id: Mapped[str | None] = mapped_column(ForeignKey("cloud_jobs.id", ondelete="SET NULL"), nullable=True)
    capability: Mapped[str] = mapped_column(String(160), index=True)
    arguments_json: Mapped[dict] = mapped_column(JSON, default=dict)
    current_step: Mapped[str | None] = mapped_column(String(160), nullable=True)
    progress: Mapped[float] = mapped_column(Float, default=0)
    attempt_count: Mapped[int] = mapped_column(Integer, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, default=3)
    available_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    claimed_by: Mapped[str | None] = mapped_column(String(160), nullable=True, index=True)
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    failure_category: Mapped[str | None] = mapped_column(String(80), nullable=True)
    safe_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    result_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    pending_action_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict)


class CloudWorkspace(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "cloud_workspaces"
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    job_id: Mapped[str] = mapped_column(ForeignKey("cloud_jobs.id", ondelete="CASCADE"), unique=True, index=True)
    project_id: Mapped[str | None] = mapped_column(ForeignKey("projects.id", ondelete="SET NULL"), nullable=True)
    status: Mapped[str] = mapped_column(String(40), default="ACTIVE", index=True)
    source_type: Mapped[str] = mapped_column(String(40), default="generated")
    git_repository: Mapped[str | None] = mapped_column(String(500), nullable=True)
    branch: Mapped[str | None] = mapped_column(String(160), nullable=True)
    storage_location: Mapped[str] = mapped_column(String(1000))
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    limits_json: Mapped[dict] = mapped_column(JSON, default=dict)


class CloudArtifact(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "cloud_artifacts"
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    job_id: Mapped[str] = mapped_column(ForeignKey("cloud_jobs.id", ondelete="CASCADE"), index=True)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("cloud_workspaces.id", ondelete="CASCADE"), index=True)
    artifact_type: Mapped[str] = mapped_column(String(80), index=True)
    name: Mapped[str] = mapped_column(String(255))
    storage_key: Mapped[str] = mapped_column(String(1000), unique=True)
    content_type: Mapped[str | None] = mapped_column(String(160), nullable=True)
    size_bytes: Mapped[int] = mapped_column(Integer, default=0)
    checksum: Mapped[str | None] = mapped_column(String(128), nullable=True)
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict)


class CloudJobEvent(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "cloud_job_events"
    __table_args__ = (UniqueConstraint("job_id", "sequence", name="uq_cloud_job_events_sequence"),)
    job_id: Mapped[str] = mapped_column(ForeignKey("cloud_jobs.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    event_type: Mapped[str] = mapped_column(String(120), index=True)
    sequence: Mapped[int] = mapped_column(Integer)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    payload_json: Mapped[dict] = mapped_column(JSON, default=dict)


class CloudCheckpoint(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "cloud_checkpoints"
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    job_id: Mapped[str] = mapped_column(ForeignKey("cloud_jobs.id", ondelete="CASCADE"), index=True)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("cloud_workspaces.id", ondelete="CASCADE"), index=True)
    step_index: Mapped[int] = mapped_column(Integer)
    state_json: Mapped[dict] = mapped_column(JSON, default=dict)
    revision_reference: Mapped[str | None] = mapped_column(String(500), nullable=True)
