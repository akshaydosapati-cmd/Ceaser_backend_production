from sqlalchemy import ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database.base import Base
from app.core.security.encryption import decrypt_text, encrypt_text
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin


class GeneratedDocument(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "generated_documents"

    file_id: Mapped[str] = mapped_column(ForeignKey("files.id", ondelete="CASCADE"), index=True, nullable=False)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    agent_id: Mapped[str] = mapped_column(String(80), index=True, nullable=False)
    template_id: Mapped[str] = mapped_column(String(120), nullable=False)
    generated_by: Mapped[str] = mapped_column(String(120), nullable=False)
    export_format: Mapped[str] = mapped_column(String(20), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    source_prompt_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)

    @property
    def source_prompt(self) -> str:
        return decrypt_text(self.source_prompt_encrypted) if self.source_prompt_encrypted else ""

    @source_prompt.setter
    def source_prompt(self, value: str | None) -> None:
        self.source_prompt_encrypted = encrypt_text(value or "")


class AgentActivity(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "agent_activity"

    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    file_id: Mapped[str | None] = mapped_column(ForeignKey("files.id", ondelete="SET NULL"), index=True, nullable=True)
    agent_id: Mapped[str] = mapped_column(String(80), index=True, nullable=False)
    action: Mapped[str] = mapped_column(String(80), nullable=False)
    detail_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)

    @property
    def detail(self) -> str:
        return decrypt_text(self.detail_encrypted) if self.detail_encrypted else ""

    @detail.setter
    def detail(self, value: str | None) -> None:
        self.detail_encrypted = encrypt_text(value or "")
