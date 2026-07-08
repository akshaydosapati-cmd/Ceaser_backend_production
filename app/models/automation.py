from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database.base import Base
from app.core.security.encryption import decrypt_text, encrypt_text
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin, utc_now


class AutomationTemplate(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "automation_templates"

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    category: Mapped[str] = mapped_column(String(80), index=True, nullable=False)
    description: Mapped[str] = mapped_column(String(1200), nullable=False)
    default_agent: Mapped[str] = mapped_column(String(80), nullable=False)
    default_prompt: Mapped[str] = mapped_column(Text, nullable=False)
    supported_frequencies: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    icon: Mapped[str] = mapped_column(String(80), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False)


class Automation(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "automations"

    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    workspace_id: Mapped[str | None] = mapped_column(String(36), index=True, nullable=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    automation_type: Mapped[str] = mapped_column(String(80), index=True, nullable=False)
    assigned_agent: Mapped[str] = mapped_column(String(80), index=True, nullable=False)
    trigger_frequency: Mapped[str] = mapped_column(String(80), nullable=False)
    trigger_time: Mapped[str | None] = mapped_column(String(20), nullable=True)
    timezone: Mapped[str] = mapped_column(String(80), default="UTC", nullable=False)
    status: Mapped[str] = mapped_column(String(40), default="active", index=True, nullable=False)
    config_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    next_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False)

    runs: Mapped[list["AutomationRun"]] = relationship(back_populates="automation", cascade="all, delete-orphan")


class AutomationRun(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "automation_runs"

    automation_id: Mapped[str] = mapped_column(ForeignKey("automations.id", ondelete="CASCADE"), index=True, nullable=False)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    workspace_id: Mapped[str | None] = mapped_column(String(36), index=True, nullable=True)
    assigned_agent: Mapped[str] = mapped_column(String(80), index=True, nullable=False)
    status: Mapped[str] = mapped_column(String(40), index=True, nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    output_title: Mapped[str | None] = mapped_column(String(255), nullable=True)
    output_summary: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    output_content_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)

    automation: Mapped[Automation] = relationship(back_populates="runs")

    @property
    def output_content(self) -> str:
        if self.output_content_encrypted:
            return decrypt_text(self.output_content_encrypted) or ""
        return ""

    @output_content.setter
    def output_content(self, value: str | None) -> None:
        self.output_content_encrypted = encrypt_text(value or "")
