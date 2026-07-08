from __future__ import annotations

import secrets

from app.services.integrations.provider_registry import ProviderRegistry
from app.services.integrations.schemas import OAuthStart, TokenPayload


class OAuthManager:
    def __init__(self):
        self.registry = ProviderRegistry()

    def start(self, provider_id: str) -> OAuthStart:
        provider = self.registry.get(provider_id)
        state = secrets.token_urlsafe(24)
        return provider.connect(state=state)

    def exchange_code(self, provider_id: str, code: str) -> TokenPayload:
        return self.registry.get(provider_id).exchange_code(code)
