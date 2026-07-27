import logging
import uuid
from typing import Annotated

import json
from collections.abc import Iterator

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.core.database.session import SessionLocal, get_db
from app.core.security.dependencies import get_current_user
from app.models.user import User
from app.schemas.ceaser import CeaserChatRequest, CeaserChatResponse
from app.services.audit_service import AuditService
from app.services.background_task_service import background_task_store
from app.services.orchestrator import CeaserOrchestrator

router = APIRouter(prefix="/ceaser", tags=["ceaser"])
logger = logging.getLogger(__name__)


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


@router.post("/chat/background")
def ceaser_chat_background(
    payload: CeaserChatRequest,
    background_tasks: BackgroundTasks,
    user: Annotated[User, Depends(get_current_user)],
):
    task_id = str(uuid.uuid4())
    background_task_store.create(task_id, user.id)
    background_tasks.add_task(_run_chat_background_task, task_id, user.id, payload)
    return {"task_id": task_id, "status": "queued"}


@router.get("/chat/background/{task_id}")
def get_ceaser_background_task(task_id: str, user: Annotated[User, Depends(get_current_user)]):
    record = background_task_store.get(task_id)
    if not record or record.user_id != user.id:
        raise HTTPException(status_code=404, detail="Task not found.")
    return {
        "task_id": record.id,
        "status": record.status,
        "result": record.result,
        "error": record.error,
        "created_at": record.created_at,
        "updated_at": record.updated_at,
    }


def _run_chat_background_task(task_id: str, user_id: str, payload: CeaserChatRequest) -> None:
    background_task_store.set_running(task_id)
    db = SessionLocal()
    try:
        response = CeaserOrchestrator(db).handle_message(
            user_id=user_id,
            message=payload.message,
            conversation_id=payload.conversation_id,
            file_ids=payload.file_ids,
        )
        background_task_store.set_result(task_id, response)
    except Exception:
        logger.exception("ceaser_background_task_failed task_id=%s user_id=%s", task_id, user_id)
        background_task_store.set_error(task_id, "We couldn't complete your request. Please try again.")
    finally:
        db.close()


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
