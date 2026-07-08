from __future__ import annotations

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
        log = AuditLog(
            user_id=user_id,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            extra_metadata=metadata or {},
        )
        self.db.add(log)
        self.db.flush()
        if commit:
            self.db.commit()
            self.db.refresh(log)
        return log
