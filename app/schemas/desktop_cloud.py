from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


class DesktopDevicePayload(BaseModel):
    device_id: str = Field(min_length=8, max_length=120)
    device_name: str = Field(default="CEASER Desktop", max_length=255)
    platform: str | None = Field(default=None, max_length=80)
    app_version: str | None = Field(default=None, max_length=80)


class DesktopDeviceRead(BaseModel):
    device_id: str
    device_name: str
    platform: str | None = None
    app_version: str | None = None
    created_at: datetime
    last_seen_at: datetime | None = None
    revoked_at: datetime | None = None
    status: str
    gateway_status: str = "offline"
    gateway_last_heartbeat_at: datetime | None = None
    capabilities: list[str] = Field(default_factory=list)


class DesktopAuthorizeRequest(DesktopDevicePayload):
    state: str = Field(min_length=8, max_length=160)
    code_challenge: str = Field(min_length=32, max_length=160)
    code_challenge_method: Literal["S256"] = "S256"
    redirect_uri: str = "ceaser://auth/callback"


class DesktopAuthorizeResponse(BaseModel):
    code: str
    state: str
    expires_in: int


class DesktopExchangeRequest(BaseModel):
    code: str = Field(min_length=16)
    code_verifier: str = Field(min_length=32, max_length=160)
    redirect_uri: str = "ceaser://auth/callback"
    device: DesktopDevicePayload


class DesktopRefreshRequest(BaseModel):
    refresh_token: str = Field(min_length=24)
    device_id: str | None = Field(default=None, max_length=120)


class DesktopRevokeRequest(BaseModel):
    refresh_token: str | None = None
    device_id: str | None = None


class DesktopSessionResponse(BaseModel):
    access_token: str
    refresh_token: str
    expires_in: int
    token_type: str = "bearer"
    user: dict[str, Any]


class DesktopCloudRequest(BaseModel):
    command: str | None = None
    resource_id: str | None = None
    resource_type: str | None = Field(default=None, max_length=80)
    query: str | None = Field(default=None, max_length=255)
    name: str | None = Field(default=None, max_length=255)
    project_id: str | None = None
    mime_type: str | None = Field(default=None, max_length=160)
    size_bytes: int | None = Field(default=None, ge=0)
    storage_path: str | None = Field(default=None, max_length=1000)
    content: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    context: dict[str, Any] = Field(default_factory=dict)


class DesktopCloudResponse(BaseModel):
    status: str
    action: str
    verified: bool = True
    message: str
    items: list[dict[str, Any]] = Field(default_factory=list)
    resource: dict[str, Any] | None = None
    signed_upload_url: str | None = None
    signed_download_url: str | None = None
    error_code: str | None = None
