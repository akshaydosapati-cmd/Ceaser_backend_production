from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class ProviderDefinition(BaseModel):
    id: str
    name: str
    category: str
    description: str
    scopes: list[str]
    permissions: list[str]
    read_only: bool = True


class OAuthStart(BaseModel):
    auth_url: str
    state: str
    provider: str
    requires_credentials: bool = False


class TokenPayload(BaseModel):
    access_token: str
    refresh_token: str | None = None
    expires_at: datetime | None = None
    provider_account_id: str | None = None
    provider_email: str | None = None
    metadata: dict = Field(default_factory=dict)
