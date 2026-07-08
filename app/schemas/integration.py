from datetime import datetime

from pydantic import BaseModel, Field


class IntegrationProviderRead(BaseModel):
    id: str
    name: str
    category: str
    description: str
    scopes: list[str]
    permissions: list[str]
    read_only: bool = True


class IntegrationRead(IntegrationProviderRead):
    status: str
    connected: bool = False
    account_email: str | None = None
    last_sync_at: str | None = None
    provider_account_id: str | None = None
    connection_id: str | None = None
    metadata: dict = Field(default_factory=dict)
    token_expires_at: str | None = None


class IntegrationConnectRequest(BaseModel):
    code: str | None = None
    workspace_id: str | None = None


class IntegrationConnectResponse(BaseModel):
    provider: str
    auth_url: str | None = None
    state: str | None = None
    requires_credentials: bool = False
    integration: IntegrationRead | None = None


class IntegrationStatusRead(BaseModel):
    provider: str
    status: str
    connected: bool
    account_email: str | None = None
    last_sync_at: str | None = None
    permissions: list[str] = Field(default_factory=list)


class IntegrationMetadataRead(BaseModel):
    provider: str
    status: str
    account_email: str | None = None
    permissions: list[str] = Field(default_factory=list)
    metadata: dict = Field(default_factory=dict)
    items: list[dict] = Field(default_factory=list)


class IntegrationRecordRead(BaseModel):
    id: str
    user_id: str
    workspace_id: str | None = None
    provider: str
    provider_account_id: str | None = None
    provider_email: str | None = None
    status: str
    token_expires_at: datetime | None = None
    metadata_json: dict = Field(default_factory=dict)
    last_sync_at: datetime | None = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
