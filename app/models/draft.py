from sqlalchemy import ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database.base import Base
from app.core.security.encryption import decrypt_json, decrypt_text, encrypt_json, encrypt_text
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin


class Draft(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "drafts"

    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    agent_id: Mapped[str] = mapped_column(String(80), index=True, nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    draft_type: Mapped[str] = mapped_column(String(80), index=True, nullable=False)
    status: Mapped[str] = mapped_column(String(40), index=True, nullable=False, default="active")
    progress: Mapped[int] = mapped_column(Integer, nullable=False, default=25)
    target_app: Mapped[str] = mapped_column(String(80), index=True, nullable=False, default="keep_as_draft")
    requested_units: Mapped[int] = mapped_column(Integer, nullable=False, default=8)
    source_prompt_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)
    content_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)

    @property
    def source_prompt(self) -> str:
        return decrypt_text(self.source_prompt_encrypted) if self.source_prompt_encrypted else ""

    @source_prompt.setter
    def source_prompt(self, value: str | None) -> None:
        self.source_prompt_encrypted = encrypt_text(value or "")

    @property
    def content(self) -> dict:
        return decrypt_json(self.content_encrypted)

    @content.setter
    def content(self, value: dict | None) -> None:
        self.content_encrypted = encrypt_json(value or {})


class DraftHistory(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "draft_history"

    draft_id: Mapped[str] = mapped_column(ForeignKey("drafts.id", ondelete="CASCADE"), index=True, nullable=False)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    agent_id: Mapped[str] = mapped_column(String(80), index=True, nullable=False)
    action: Mapped[str] = mapped_column(String(80), nullable=False)
    detail_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)

    @property
    def detail(self) -> str:
        return decrypt_text(self.detail_encrypted) if self.detail_encrypted else ""

    @detail.setter
    def detail(self, value: str | None) -> None:
        self.detail_encrypted = encrypt_text(value or "")
