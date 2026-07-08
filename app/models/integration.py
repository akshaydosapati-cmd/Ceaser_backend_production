from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database.base import Base
from app.core.security.encryption import decrypt_text, encrypt_text
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin, utc_now


class Integration(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "integrations"

    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    workspace_id: Mapped[str | None] = mapped_column(String(36), index=True, nullable=True)
    provider: Mapped[str] = mapped_column(String(80), index=True, nullable=False)
    provider_account_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    provider_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    status: Mapped[str] = mapped_column(String(40), default="not_connected", index=True, nullable=False)
    access_token_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)
    refresh_token_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)
    token_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    last_sync_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False)

    @property
    def access_token(self) -> str:
        if self.access_token_encrypted:
            return decrypt_text(self.access_token_encrypted) or ""
        return ""

    @access_token.setter
    def access_token(self, value: str | None) -> None:
        self.access_token_encrypted = encrypt_text(value or "") if value else None

    @property
    def refresh_token(self) -> str:
        if self.refresh_token_encrypted:
            return decrypt_text(self.refresh_token_encrypted) or ""
        return ""

    @refresh_token.setter
    def refresh_token(self, value: str | None) -> None:
        self.refresh_token_encrypted = encrypt_text(value or "") if value else None
