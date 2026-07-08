from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.core.database.session import get_db
from app.core.security.access_control import require_conversation_access
from app.core.security.dependencies import get_current_user
from app.models.user import User
from app.schemas.voice import (
    VoiceRespondResponse,
    VoiceSessionRead,
    VoiceSettingsRead,
    VoiceSettingsUpdate,
    VoiceSpeakRequest,
    VoiceSpeakResponse,
    VoiceTranscribeResponse,
)
from app.services.audit_service import AuditService
from app.services.voice.voice_manager import VoiceManager
from app.services.voice.voice_session import VoiceSessionManager
from app.services.voice.voice_settings import VoiceSettingsService

router = APIRouter(prefix="/voice", tags=["voice"])


@router.post("/transcribe", response_model=VoiceTranscribeResponse)
async def transcribe_voice(user: Annotated[User, Depends(get_current_user)], db: Annotated[Session, Depends(get_db)], audio: UploadFile = File(...), language: str | None = None):
    settings = VoiceSettingsService(db).get_or_create(user.id)
    content = await audio.read()
    try:
        transcript = VoiceManager(db).transcribe(content, content_type=audio.content_type or "audio/webm", language=language or settings.language)
        AuditService(db).record(user_id=user.id, action="voice_transcribed", resource_type="voice", metadata={"bytes": len(content)})
        return {"transcript": transcript}
    except Exception as exc:
        AuditService(db).record(user_id=user.id, action="voice_failed", resource_type="voice", metadata={"stage": "transcribe", "error": str(exc)})
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.post("/respond", response_model=VoiceRespondResponse)
async def respond_with_voice(
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
    audio: UploadFile = File(...),
    conversation_id: str | None = None,
):
    if conversation_id:
        require_conversation_access(db, user, conversation_id)
    content = await audio.read()
    AuditService(db).record(user_id=user.id, action="voice_started", resource_type="voice", resource_id=conversation_id)
    try:
        result = VoiceManager(db).respond(user_id=user.id, audio=content, content_type=audio.content_type or "audio/webm", conversation_id=conversation_id)
        AuditService(db).record(
            user_id=user.id,
            action="voice_response_generated",
            resource_type="voice",
            resource_id=result.session_id,
            metadata={"conversation_id": result.chat.conversation_id, "transcript_length": len(result.transcript)},
        )
        AuditService(db).record(user_id=user.id, action="voice_completed", resource_type="voice", resource_id=result.session_id)
        return result
    except Exception as exc:
        AuditService(db).record(user_id=user.id, action="voice_failed", resource_type="voice", metadata={"stage": "respond", "error": str(exc)})
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.post("/speak", response_model=VoiceSpeakResponse)
def speak_voice(payload: VoiceSpeakRequest, user: Annotated[User, Depends(get_current_user)], db: Annotated[Session, Depends(get_db)]):
    try:
        return VoiceManager(db).speak(payload.text, voice_id=payload.voice_id)
    except Exception as exc:
        AuditService(db).record(user_id=user.id, action="voice_failed", resource_type="voice", metadata={"stage": "speak", "error": str(exc)})
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.get("/settings", response_model=VoiceSettingsRead)
def get_voice_settings(user: Annotated[User, Depends(get_current_user)], db: Annotated[Session, Depends(get_db)]):
    return VoiceSettingsService(db).get_or_create(user.id)


@router.put("/settings", response_model=VoiceSettingsRead)
def update_voice_settings(payload: VoiceSettingsUpdate, user: Annotated[User, Depends(get_current_user)], db: Annotated[Session, Depends(get_db)]):
    record = VoiceSettingsService(db).update(user.id, payload.model_dump(exclude_unset=True))
    db.commit()
    db.refresh(record)
    return record


@router.get("/session/{session_id}", response_model=VoiceSessionRead)
def get_voice_session(session_id: str, user: Annotated[User, Depends(get_current_user)], db: Annotated[Session, Depends(get_db)]):
    session = VoiceSessionManager(db).get(session_id)
    if not session or session.user_id != user.id:
        raise HTTPException(status_code=404, detail="Voice session not found.")
    return session
