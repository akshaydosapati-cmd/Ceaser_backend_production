from typing import Annotated

import json
from collections.abc import Iterator

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
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


@router.post("/chat/stream")
def ceaser_chat_stream(payload: CeaserChatRequest, user: Annotated[User, Depends(get_current_user)], db: Annotated[Session, Depends(get_db)]):
    def event(event_type: str, data: dict | str) -> str:
        payload_text = data if isinstance(data, str) else json.dumps(data, ensure_ascii=True)
        return f"event: {event_type}\ndata: {payload_text}\n\n"

    def stream() -> Iterator[str]:
        yield event("status", {"state": "understanding_request"})
        yield event("status", {"state": "retrieving_context"})
        response = CeaserOrchestrator(db).handle_message(
            user_id=user.id,
            message=payload.message,
            conversation_id=payload.conversation_id,
            file_ids=payload.file_ids,
        )
        yield event("status", {"state": "generating"})
        for chunk in _chunk_text(response.get("response", "")):
            yield event("token", chunk)
        AuditService(db).record(
            user_id=user.id,
            action="message_created",
            resource_type="conversation",
            resource_id=payload.conversation_id,
            metadata={"selected_agents": response.get("selected_agents", []), "memory_count": len(response.get("memories_used", []))},
        )
        yield event("complete", response)

    return StreamingResponse(stream(), media_type="text/event-stream")


def _chunk_text(text: str, max_chars: int = 120) -> list[str]:
    if not text:
        return []
    chunks: list[str] = []
    buffer = ""
    for piece in text.split():
        candidate = f"{buffer} {piece}".strip()
        if len(candidate) > max_chars and buffer:
            chunks.append(buffer)
            buffer = piece
        else:
            buffer = candidate
    if buffer:
        chunks.append(buffer)
    return chunks
