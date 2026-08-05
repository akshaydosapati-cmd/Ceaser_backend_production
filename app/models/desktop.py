from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database.base import Base
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin


class DesktopAuthCode(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "desktop_auth_codes"

    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    code_hash: Mapped[str] = mapped_column(String(128), unique=True, index=True, nullable=False)
    state: Mapped[str] = mapped_column(String(160), index=True, nullable=False)
    code_challenge: Mapped[str] = mapped_column(String(160), nullable=False)
    code_challenge_method: Mapped[str] = mapped_column(String(16), default="S256", nullable=False)
    device_id: Mapped[str] = mapped_column(String(120), index=True, nullable=False)
    device_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    platform: Mapped[str | None] = mapped_column(String(80), nullable=True)
    app_version: Mapped[str | None] = mapped_column(String(80), nullable=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class DesktopRefreshSession(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "desktop_refresh_sessions"

    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    device_id: Mapped[str] = mapped_column(String(120), index=True, nullable=False)
    token_hash: Mapped[str] = mapped_column(String(128), unique=True, index=True, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class DesktopDevice(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "desktop_devices"

    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    device_id: Mapped[str] = mapped_column(String(120), index=True, nullable=False)
    device_name: Mapped[str] = mapped_column(String(255), nullable=False)
    platform: Mapped[str | None] = mapped_column(String(80), nullable=True)
    app_version: Mapped[str | None] = mapped_column(String(80), nullable=True)
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class DesktopCloudResource(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "desktop_cloud_resources"

    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    project_id: Mapped[str | None] = mapped_column(ForeignKey("projects.id", ondelete="SET NULL"), index=True, nullable=True)
    name: Mapped[str] = mapped_column(String(255), index=True, nullable=False)
    resource_type: Mapped[str] = mapped_column(String(80), index=True, nullable=False)
    mime_type: Mapped[str | None] = mapped_column(String(160), nullable=True)
    storage_path: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    status: Mapped[str] = mapped_column(String(40), index=True, default="active", nullable=False)
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    content_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)
