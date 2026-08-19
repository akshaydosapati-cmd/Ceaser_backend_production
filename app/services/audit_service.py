from __future__ import annotations

from uuid import NAMESPACE_URL, uuid5

from sqlalchemy.orm import Session

from app.models.audit_log import AuditLog


class AuditService:
    def __init__(self, db: Session):
        self.db = db

    def record(
        self,
        *,
        user_id: str,
        action: str,
        resource_type: str,
        resource_id: str | None = None,
        metadata: dict | None = None,
        commit: bool = True,
    ) -> AuditLog:
        safe_metadata = dict(metadata or {})
        normalized_resource_id = resource_id
        if resource_id and len(resource_id) > 36:
            safe_metadata.setdefault("resource_reference", resource_id)
            normalized_resource_id = str(uuid5(NAMESPACE_URL, resource_id))
        log = AuditLog(
            user_id=user_id,
            action=action,
            resource_type=resource_type,
            resource_id=normalized_resource_id,
            extra_metadata=safe_metadata,
        )
        self.db.add(log)
        self.db.flush()
        if commit:
            self.db.commit()
            self.db.refresh(log)
        return log
