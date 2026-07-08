from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from app.schemas.ceaser import CeaserChatResponse
from app.schemas.common import ORMModel


class VoiceTranscribeResponse(BaseModel):
    transcript: str


class VoiceSpeakRequest(BaseModel):
    text: str = Field(min_length=1)
    voice_id: str | None = None


class VoiceSpeakResponse(BaseModel):
    audio_base64: str
    content_type: str


class VoiceRespondResponse(BaseModel):
    session_id: str
    transcript: str
    chat: CeaserChatResponse
    spoken_summary: str
    audio_base64: str | None = None
    audio_content_type: str | None = None
    voice_warning: str | None = None


class VoiceSettingsRead(ORMModel):
    id: str
    user_id: str
    voice_enabled: bool
    auto_speak_responses: bool
    voice_provider: str
    preferred_voice: str | None = None
    speech_speed: float
    speech_volume: float
    language: str


class VoiceSettingsUpdate(BaseModel):
    voice_enabled: bool = True
    auto_speak_responses: bool = True
    voice_provider: str = Field(default="auto", pattern="^(auto|browser|elevenlabs)$")
    preferred_voice: str | None = None
    speech_speed: float = Field(default=1.0, ge=0.5, le=2.0)
    speech_volume: float = Field(default=1.0, ge=0.0, le=1.0)
    language: str = "en"


class VoiceSessionRead(ORMModel):
    id: str
    user_id: str
    conversation_id: str | None = None
    status: str
    started_at: datetime | None = None
    ended_at: datetime | None = None
    error_message: str | None = None
