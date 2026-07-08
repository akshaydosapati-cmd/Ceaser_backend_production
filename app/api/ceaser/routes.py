from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database.session import get_db
from app.core.security.dependencies import get_current_user
from app.models.user import User
from app.schemas.ceaser import CeaserChatRequest, CeaserChatResponse
from app.services.audit_service import AuditService
from app.services.orchestrator import CeaserOrchestrator

router = APIRouter(prefix="/ceaser", tags=["ceaser"])


@router.post("/chat", response_model=CeaserChatResponse)
def ceaser_chat(payload: CeaserChatRequest, user: Annotated[User, Depends(get_current_user)], db: Annotated[Session, Depends(get_db)]):
    try:
        response = CeaserOrchestrator(db).handle_message(
            user_id=user.id,
            message=payload.message,
            conversation_id=payload.conversation_id,
            file_ids=payload.file_ids,
        )
        AuditService(db).record(
            user_id=user.id,
            action="message_created",
            resource_type="conversation",
            resource_id=payload.conversation_id,
            metadata={"selected_agents": response.get("selected_agents", []), "memory_count": len(response.get("memories_used", []))},
        )
        return response
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
