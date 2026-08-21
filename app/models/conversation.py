from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, JSON, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database.base import Base
from app.core.security.encryption import decrypt_json, decrypt_text, encrypt_json, encrypt_text
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin


class Conversation(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "conversations"

    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    pinned: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    archived: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    raw_summary: Mapped[str | None] = mapped_column("conversation_summary", String, nullable=True)
    summary_encrypted: Mapped[str | None] = mapped_column(String, nullable=True)
    raw_state: Mapped[dict] = mapped_column("conversation_state", JSON, default=dict, nullable=False)
    state_encrypted: Mapped[str | None] = mapped_column(String, nullable=True)
    summary_version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    state_updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    messages: Mapped[list["Message"]] = relationship(back_populates="conversation", cascade="all, delete-orphan")

    @property
    def conversation_summary(self) -> str | None:
        if self.summary_encrypted:
            return decrypt_text(self.summary_encrypted)
        return self.raw_summary

    @conversation_summary.setter
    def conversation_summary(self, value: str | None) -> None:
        self.summary_encrypted = encrypt_text(value) if value else None
        self.raw_summary = "[encrypted]" if value else None

    @property
    def conversation_state(self) -> dict:
        if self.state_encrypted:
            return decrypt_json(self.state_encrypted)
        return self.raw_state or {}

    @conversation_state.setter
    def conversation_state(self, value: dict | None) -> None:
        self.state_encrypted = encrypt_json(value or {})
        self.raw_state = {}


class Message(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "messages"

    conversation_id: Mapped[str] = mapped_column(ForeignKey("conversations.id", ondelete="CASCADE"), index=True, nullable=False)
    role: Mapped[str] = mapped_column(String(30), nullable=False)
    raw_content: Mapped[str] = mapped_column("content", String, nullable=False, default="[encrypted]")
    content_encrypted: Mapped[str | None] = mapped_column(String, nullable=True)
    raw_metadata: Mapped[dict] = mapped_column("metadata", JSON, default=dict, nullable=False)
    metadata_encrypted: Mapped[str | None] = mapped_column(String, nullable=True)

    conversation: Mapped["Conversation"] = relationship(back_populates="messages")

    @property
    def content(self) -> str:
        if self.content_encrypted:
            return decrypt_text(self.content_encrypted) or ""
        return self.raw_content

    @content.setter
    def content(self, value: str) -> None:
        self.content_encrypted = encrypt_text(value)
        self.raw_content = "[encrypted]"

    @property
    def extra_metadata(self) -> dict:
        if self.metadata_encrypted:
            return decrypt_json(self.metadata_encrypted)
        return self.raw_metadata or {}

    @extra_metadata.setter
    def extra_metadata(self, value: dict | None) -> None:
        self.metadata_encrypted = encrypt_json(value or {})
        self.raw_metadata = {}
