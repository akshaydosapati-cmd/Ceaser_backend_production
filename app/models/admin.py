from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database.base import Base
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin


class DownloadEvent(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "download_events"

    user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), index=True, nullable=True)
    source: Mapped[str] = mapped_column(String(80), default="website", index=True, nullable=False)
    platform: Mapped[str] = mapped_column(String(80), default="windows", index=True, nullable=False)
    version: Mapped[str | None] = mapped_column(String(80), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(String(500), nullable=True)
    ip_hash: Mapped[str | None] = mapped_column(String(128), index=True, nullable=True)
