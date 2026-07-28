from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.database.session import get_db
from app.core.security.access_control import require_conversation_access
from app.core.security.dependencies import get_current_user
from app.models.user import User
from app.schemas.conversation import MessageCreate, MessageRead
from app.services.audit_service import AuditService
from app.services.conversation_service import ConversationService

router = APIRouter(prefix="/messages", tags=["messages"])
chat_router = APIRouter(prefix="/chat", tags=["chat"])


@router.get("", response_model=list[MessageRead])
def list_messages(user: Annotated[User, Depends(get_current_user)], db: Annotated[Session, Depends(get_db)], conversation_id: str | None = None, limit: int = 100, offset: int = 0):
    if not conversation_id:
        raise HTTPException(status_code=400, detail="conversation_id is required")
    require_conversation_access(db, user, conversation_id)
    messages = ConversationService(db).list_messages(conversation_id=conversation_id, limit=limit, offset=offset)
    AuditService(db).record(user_id=user.id, action="message_read", resource_type="conversation", resource_id=conversation_id, metadata={"count": len(messages)})
    return messages


@router.post("", response_model=MessageRead, status_code=status.HTTP_201_CREATED)
def create_message(payload: MessageCreate, user: Annotated[User, Depends(get_current_user)], db: Annotated[Session, Depends(get_db)]):
    if not payload.conversation_id:
        raise HTTPException(status_code=400, detail="conversation_id is required")
    require_conversation_access(db, user, payload.conversation_id)
    message = ConversationService(db).create_message(
        conversation_id=payload.conversation_id,
        role=payload.role,
        content=payload.content,
        metadata=payload.metadata,
        ingest_knowledge=False,
    )
    AuditService(db).record(user_id=user.id, action="message_created", resource_type="message", resource_id=message.id)
    return message


@chat_router.get("/conversations/{conversation_id}/messages", response_model=list[MessageRead])
def chat_messages(
    conversation_id: str,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
    limit: int = 60,
    offset: int = 0,
):
    require_conversation_access(db, user, conversation_id)
    messages = ConversationService(db).list_messages(conversation_id=conversation_id, limit=limit, offset=offset)
    return messages


@chat_router.post("/conversations/{conversation_id}/messages", response_model=MessageRead, status_code=status.HTTP_201_CREATED)
def chat_send_message(conversation_id: str, payload: MessageCreate, user: Annotated[User, Depends(get_current_user)], db: Annotated[Session, Depends(get_db)]):
    require_conversation_access(db, user, conversation_id)
    message = ConversationService(db).create_message(
        conversation_id=conversation_id,
        role=payload.role,
        content=payload.content,
        metadata=payload.metadata,
        ingest_knowledge=False,
    )
    AuditService(db).record(user_id=user.id, action="message_created", resource_type="message", resource_id=message.id)
    return message
