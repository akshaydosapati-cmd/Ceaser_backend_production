from __future__ import annotations

from sqlalchemy.orm import Session

from app.models.integration import Integration


class ConnectionService:
    def __init__(self, db: Session):
        self.db = db

    def list(self, user_id: str) -> list[Integration]:
        return self.db.query(Integration).filter(Integration.user_id == user_id).order_by(Integration.provider.asc()).all()

    def get(self, user_id: str, provider: str) -> Integration | None:
        return self.db.query(Integration).filter(Integration.user_id == user_id, Integration.provider == provider).first()

    def get_by_oauth_state(self, provider: str, state: str) -> Integration | None:
        candidates = self.db.query(Integration).filter(Integration.provider == provider).all()
        for integration in candidates:
            if (integration.metadata_json or {}).get("oauth_state") == state:
                return integration
        return None

    def get_or_create(self, user_id: str, provider: str, workspace_id: str | None = None) -> Integration:
        integration = self.get(user_id=user_id, provider=provider)
        if integration:
            return integration
        integration = Integration(user_id=user_id, provider=provider, workspace_id=workspace_id, status="not_connected", metadata_json={})
        self.db.add(integration)
        self.db.flush()
        return integration
