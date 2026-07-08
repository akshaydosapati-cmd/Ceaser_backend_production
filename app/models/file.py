from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database.base import Base
from app.core.security.encryption import decrypt_json, decrypt_text, encrypt_json, encrypt_text
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin


class File(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "files"

    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    project_id: Mapped[str | None] = mapped_column(ForeignKey("projects.id", ondelete="SET NULL"), index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    file_type: Mapped[str] = mapped_column(String(80), nullable=False)
    storage_path: Mapped[str] = mapped_column(String(1000), nullable=False)
    extracted_content_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)
    extraction_metadata_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)

    project: Mapped["Project | None"] = relationship(back_populates="files")

    @property
    def extracted_content(self) -> str:
        if self.extracted_content_encrypted:
            return decrypt_text(self.extracted_content_encrypted) or ""
        return ""

    @extracted_content.setter
    def extracted_content(self, value: str | None) -> None:
        self.extracted_content_encrypted = encrypt_text(value or "")

    @property
    def extraction_metadata(self) -> dict:
        if self.extraction_metadata_encrypted:
            return decrypt_json(self.extraction_metadata_encrypted)
        return {}

    @extraction_metadata.setter
    def extraction_metadata(self, value: dict | None) -> None:
        self.extraction_metadata_encrypted = encrypt_json(value or {})
