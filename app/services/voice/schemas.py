from __future__ import annotations

from pydantic import BaseModel, Field

from app.schemas.ceaser import CeaserChatResponse


class TranscriptionResult(BaseModel):
    text: str


class SpeechResult(BaseModel):
    audio_base64: str
    content_type: str = "audio/mpeg"


class VoiceRespondResult(BaseModel):
    session_id: str
    transcript: str
    chat: CeaserChatResponse
    spoken_summary: str
    audio_base64: str | None = None
    audio_content_type: str | None = None
    voice_warning: str | None = None


class VoiceSettingsData(BaseModel):
    voice_enabled: bool = True
    auto_speak_responses: bool = True
    voice_provider: str = "auto"
    preferred_voice: str | None = None
    speech_speed: float = Field(default=1.0, ge=0.5, le=2.0)
    speech_volume: float = Field(default=1.0, ge=0.0, le=1.0)
    language: str = "en"
