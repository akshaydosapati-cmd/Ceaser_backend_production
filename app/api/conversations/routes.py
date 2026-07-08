from typing import Annotated

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.core.database.session import get_db
from app.core.security.access_control import require_conversation_access
from app.core.security.dependencies import get_current_user
from app.models.user import User
from app.schemas.conversation import ConversationCreate, ConversationRead, ConversationUpdate
from app.services.conversation_service import ConversationService

router = APIRouter(prefix="/conversations", tags=["conversations"])


@router.get("", response_model=list[ConversationRead])
def list_conversations(
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
    archived: bool = False,
    limit: int = 50,
    offset: int = 0,
):
    return ConversationService(db).list(user_id=user.id, limit=limit, offset=offset, archived=archived)


@router.post("", response_model=ConversationRead, status_code=status.HTTP_201_CREATED)
def create_conversation(payload: ConversationCreate, user: Annotated[User, Depends(get_current_user)], db: Annotated[Session, Depends(get_db)]):
    return ConversationService(db).create(user_id=user.id, title=payload.title)


@router.get("/{conversation_id}", response_model=ConversationRead)
def get_conversation(conversation_id: str, user: Annotated[User, Depends(get_current_user)], db: Annotated[Session, Depends(get_db)]):
    return require_conversation_access(db, user, conversation_id)


@router.patch("/{conversation_id}", response_model=ConversationRead)
def update_conversation(conversation_id: str, payload: ConversationUpdate, user: Annotated[User, Depends(get_current_user)], db: Annotated[Session, Depends(get_db)]):
    conversation = require_conversation_access(db, user, conversation_id)
    return ConversationService(db).update(conversation, title=payload.title, pinned=payload.pinned, archived=payload.archived)


@router.delete("/{conversation_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_conversation(conversation_id: str, user: Annotated[User, Depends(get_current_user)], db: Annotated[Session, Depends(get_db)]):
    ConversationService(db).delete(require_conversation_access(db, user, conversation_id))
    return None
