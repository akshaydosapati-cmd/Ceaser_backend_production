from sqlalchemy import ForeignKey, JSON, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database.base import Base
from app.core.security.encryption import decrypt_json, decrypt_text, encrypt_json, encrypt_text
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin


class Memory(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "memories"

    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    memory_type: Mapped[str] = mapped_column(String(80), nullable=False)
    raw_content: Mapped[str] = mapped_column("content", String, nullable=False, default="[encrypted]")
    content_encrypted: Mapped[str | None] = mapped_column(String, nullable=True)
    raw_metadata: Mapped[dict] = mapped_column("metadata", JSON, default=dict, nullable=False)
    metadata_encrypted: Mapped[str | None] = mapped_column(String, nullable=True)

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
