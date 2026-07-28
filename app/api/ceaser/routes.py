import logging
import uuid
from typing import Annotated

import json
from collections.abc import AsyncIterator
from time import perf_counter

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
            request_id=payload.request_id,
            parent_message_id=payload.parent_message_id,
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
            request_id=payload.request_id,
            parent_message_id=payload.parent_message_id,
        )
        background_task_store.set_result(task_id, response)
    except Exception:
        logger.exception("ceaser_background_task_failed task_id=%s user_id=%s", task_id, user_id)
        background_task_store.set_error(task_id, "We couldn't complete your request. Please try again.")
    finally:
        db.close()


@router.post("/chat/stream")
async def ceaser_chat_stream(payload: CeaserChatRequest, user: Annotated[User, Depends(get_current_user)], db: Annotated[Session, Depends(get_db)]):
    user_id = user.id
    message = payload.message
    conversation_id = payload.conversation_id
    file_ids = list(payload.file_ids)
    request_id = str(uuid.uuid4())
    logger.info("ceaser_stream_stage request_id=%s stage=request_received conversation_id=%s", request_id, conversation_id)
    logger.info("ceaser_stream_stage request_id=%s stage=authentication_complete user_id=%s", request_id, user_id)

    def event(event_type: str, data: dict | str) -> str:
        payload_text = data if isinstance(data, str) else json.dumps(data, ensure_ascii=True)
        return f"event: {event_type}\ndata: {payload_text}\n\n"

    async def stream() -> AsyncIterator[str]:
        started = perf_counter()
        stage_marks: dict[str, float] = {"start": started}
        trace: dict[str, object] = {"request_id": request_id}
        first_sse_token_logged = False
        try:
            yield event("status", {"state": "received"})
            yield event("status", {"state": "understanding_request"})
            orchestrator = CeaserOrchestrator(db)
            logger.info("ceaser_stream_stage request_id=%s stage=retrieval_started", request_id)
            prepared = orchestrator.prepare_stream_request(
                user_id=user_id,
                message=message,
                conversation_id=conversation_id,
                file_ids=file_ids,
                request_id=payload.request_id or request_id,
                parent_message_id=payload.parent_message_id,
            )
            stage_marks["prepared"] = perf_counter()
            trace["retrieval_time_ms"] = prepared.get("observability", {}).get("retrieval_time_ms")
            logger.info(
                "ceaser_stream_stage request_id=%s stage=intent_complete intent_ms=%s",
                request_id,
                prepared.get("observability", {}).get("intent_ms"),
            )
            logger.info(
                "ceaser_stream_stage request_id=%s stage=retrieval_complete retrieval_time_ms=%s",
                request_id,
                prepared.get("observability", {}).get("retrieval_time_ms"),
            )
            logger.info(
                "ceaser_stream_stage request_id=%s stage=context_complete context_tokens=%s prepare_ms=%s retrieval_scope=%s retrieval_sources=%s",
                request_id,
                prepared.get("observability", {}).get("context_tokens"),
                prepared.get("observability", {}).get("prepare_ms"),
                prepared.get("observability", {}).get("retrieval_scope"),
                prepared.get("observability", {}).get("retrieval_sources"),
            )

            if prepared["mode"] == "direct":
                yield event("status", {"state": "generating"})
                trace["endpoint_ttft_ms"] = round((perf_counter() - started) * 1000, 2)
                trace["total_time_ms"] = trace["endpoint_ttft_ms"]
                trace["output_tokens"] = max(1, round(len(prepared["response"]) / 4)) if prepared.get("response") else 0
                yield event("token", prepared["response"])
                first_sse_token_logged = True
                logger.info(
                    "ceaser_stream_stage request_id=%s stage=first_sse_token endpoint_ttft_ms=%s",
                    request_id,
                    trace["endpoint_ttft_ms"],
                )
                prepared["stream_trace"] = trace
                response = orchestrator.finalize_stream_response(prepared, prepared["response"])
                yield event("complete", response)
                logger.info("ceaser_stream_stage request_id=%s stage=request_complete total_ms=%s", request_id, trace["total_time_ms"])
                return

            yield event("status", {"state": "retrieving_context"})
            stage_marks["context_ready"] = perf_counter()
            yield event("status", {"state": "generating"})
            chunks: list[str] = []
            async for chunk in orchestrator.response_pipeline.stream(
                prepared["effective_message"],
                prepared["context"],
                trace=trace,
            ):
                chunks.append(chunk)
                if not first_sse_token_logged:
                    trace["endpoint_ttft_ms"] = round((perf_counter() - started) * 1000, 2)
                    logger.info(
                        "ceaser_stream_stage request_id=%s stage=first_sse_token endpoint_ttft_ms=%s",
                        request_id,
                        trace["endpoint_ttft_ms"],
                    )
                    first_sse_token_logged = True
                yield event("token", chunk)
            response_text = "".join(chunks).strip()
            trace["output_tokens"] = max(1, round(len(response_text) / 4)) if response_text else 0
            trace["total_time_ms"] = round((perf_counter() - started) * 1000, 2)
            prepared["stream_trace"] = trace
            response = orchestrator.finalize_stream_response(prepared, response_text)
            stage_marks["complete"] = perf_counter()
            logger.info(
                "ceaser_stream_trace user_id=%s conversation_id=%s prepare_ms=%s context_ms=%s provider=%s model=%s fallback=%s first_token_ms=%s total_ms=%s",
                user_id,
                conversation_id,
                round((stage_marks.get("prepared", started) - started) * 1000, 2),
                round((stage_marks.get("context_ready", stage_marks.get("prepared", started)) - stage_marks.get("prepared", started)) * 1000, 2),
                trace.get("provider"),
                trace.get("model"),
                trace.get("fallback"),
                trace.get("first_token_ms"),
                round((stage_marks["complete"] - started) * 1000, 2),
            )
            logger.info(
                "ceaser_stream_stage request_id=%s stage=generation_complete provider=%s model=%s fallback_used=%s fallback_from=%s upstream_ttft_ms=%s provider_connect_ms=%s provider_generation_ms=%s output_tokens=%s",
                request_id,
                trace.get("provider"),
                trace.get("model"),
                trace.get("fallback_used"),
                trace.get("fallback_from"),
                trace.get("first_token_ms"),
                trace.get("provider_connect_ms"),
                trace.get("provider_generation_ms"),
                trace.get("output_tokens"),
            )
            AuditService(db).record(
                user_id=user_id,
                action="message_created",
                resource_type="conversation",
                resource_id=conversation_id,
                metadata={"selected_agents": response.get("selected_agents", []), "memory_count": len(response.get("memories_used", []))},
            )
            yield event("complete", response)
            logger.info("ceaser_stream_stage request_id=%s stage=request_complete total_ms=%s", request_id, trace.get("total_time_ms"))
        except ValueError as exc:
            yield event("error", {"message": str(exc)})
        except Exception:
            logger.exception("ceaser_chat_stream_failed user_id=%s conversation_id=%s", user_id, conversation_id)
            yield event("error", {"message": "We couldn't complete your request. Please try again."})

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
