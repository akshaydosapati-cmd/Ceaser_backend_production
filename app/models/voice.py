from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database.base import Base
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin


class VoiceSession(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "voice_sessions"

    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    conversation_id: Mapped[str | None] = mapped_column(ForeignKey("conversations.id", ondelete="SET NULL"), index=True, nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="listening")
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error_message: Mapped[str | None] = mapped_column(String(500), nullable=True)


class VoiceSettings(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "voice_settings"

    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), unique=True, index=True, nullable=False)
    voice_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    auto_speak_responses: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    voice_provider: Mapped[str] = mapped_column(String(32), nullable=False, default="auto")
    preferred_voice: Mapped[str | None] = mapped_column(String(255), nullable=True)
    speech_speed: Mapped[float] = mapped_column(Float, nullable=False, default=1.0)
    speech_volume: Mapped[float] = mapped_column(Float, nullable=False, default=1.0)
    language: Mapped[str] = mapped_column(String(20), nullable=False, default="en")

    user: Mapped["User"] = relationship()
