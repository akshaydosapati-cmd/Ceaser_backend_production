from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.database.session import get_db
from app.core.security.dependencies import get_current_user
from app.models.user import User
from app.schemas.desktop import DesktopIntentRequest, DesktopIntentResponse
from app.services.audit_service import AuditService
from app.services.desktop_intent_classifier import DesktopIntentClassifier

router = APIRouter(prefix="/desktop", tags=["desktop"])


@router.post("/intent", response_model=DesktopIntentResponse)
def classify_desktop_intent(payload: DesktopIntentRequest, user: Annotated[User, Depends(get_current_user)], db: Annotated[Session, Depends(get_db)]):
    AuditService(db).record(
        user_id=user.id,
        action="desktop_command_received",
        resource_type="desktop",
        metadata={"command_length": len(payload.command), "command_preview": payload.command[:32]},
        commit=False,
    )
    result = DesktopIntentClassifier().classify(payload.command)
    AuditService(db).record(
        user_id=user.id,
        action="desktop_intent_classified",
        resource_type="desktop",
        metadata={"intent": result["intent"], "action": result["action"], "active_agent": result.get("active_agent")},
    )
    return result
