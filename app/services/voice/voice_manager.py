from __future__ import annotations

import base64
import re

from sqlalchemy.orm import Session

from app.core.config.settings import settings
from app.repositories.conversation_repository import ConversationRepository
from app.services.orchestrator import CeaserOrchestrator
from app.services.voice.providers import DeepgramProvider, ElevenLabsProvider
from app.services.voice.schemas import SpeechResult, VoiceRespondResult
from app.services.voice.speech_to_text import STTProvider
from app.services.voice.text_to_speech import TTSProvider
from app.services.voice.voice_session import VoiceSessionManager
from app.services.voice.voice_settings import VoiceSettingsService


class VoiceManager:
    def __init__(self, db: Session):
        self.db = db
        self.sessions = VoiceSessionManager(db)
        self.settings = VoiceSettingsService(db)

    def stt_provider(self) -> STTProvider:
        if settings.stt_provider.lower() == "deepgram":
            return DeepgramProvider()
        raise RuntimeError(f"Unsupported STT provider: {settings.stt_provider}")

    def tts_provider(self) -> TTSProvider:
        if settings.tts_provider.lower() == "elevenlabs":
            return ElevenLabsProvider()
        raise RuntimeError(f"Unsupported TTS provider: {settings.tts_provider}")

    def transcribe(self, audio: bytes, *, content_type: str, language: str) -> str:
        return self.stt_provider().transcribe(audio, content_type=content_type, language=language)

    def speak(self, text: str, *, voice_id: str | None = None) -> SpeechResult:
        audio, content_type = self.tts_provider().speak(text, voice_id=voice_id)
        return SpeechResult(audio_base64=base64.b64encode(audio).decode("ascii"), content_type=content_type)

    def respond(
        self,
        *,
        user_id: str,
        audio: bytes,
        content_type: str,
        conversation_id: str | None,
    ) -> VoiceRespondResult:
        voice_settings = self.settings.get_or_create(user_id)
        session = self.sessions.start(user_id=user_id, conversation_id=conversation_id)
        try:
            try:
                transcript = self.transcribe(audio, content_type=content_type, language=voice_settings.language)
            except Exception as exc:
                raise RuntimeError(f"Deepgram transcription failed: {exc}") from exc
            self.sessions.set_status(session, "processing")
            chat = CeaserOrchestrator(self.db).handle_message(
                user_id=user_id,
                message=transcript,
                conversation_id=conversation_id,
            )
            if chat.get("conversation_id") and session.conversation_id != chat.get("conversation_id"):
                session.conversation_id = chat.get("conversation_id")
                self.db.flush()
            self.sessions.set_status(session, "speaking")
            spoken_summary = self.condense_for_speech(chat.get("response", ""))
            speech = None
            voice_warning = None
            if voice_settings.auto_speak_responses and spoken_summary and voice_settings.voice_provider != "browser":
                try:
                    speech = self.speak(spoken_summary, voice_id=voice_settings.preferred_voice)
                except Exception as exc:
                    voice_warning = "Voice playback unavailable. Using fallback voice."
            self.sessions.set_status(session, "completed")
            return VoiceRespondResult(
                session_id=session.id,
                transcript=transcript,
                chat=chat,
                spoken_summary=spoken_summary,
                audio_base64=speech.audio_base64 if speech else None,
                audio_content_type=speech.content_type if speech else None,
                voice_warning=voice_warning,
            )
        except Exception as exc:
            self.sessions.set_status(session, "error", str(exc))
            raise

    def ensure_conversation(self, user_id: str, conversation_id: str | None = None) -> str:
        if conversation_id:
            return conversation_id
        conversation = ConversationRepository(self.db).create(user_id=user_id, title="Voice Conversation")
        self.db.flush()
        return conversation.id

    @staticmethod
    def condense_for_speech(text: str, max_sentences: int = 3) -> str:
        without_urls = re.sub(r"https?://\S+", "", text)
        without_markdown = re.sub(r"^#{1,6}\s*", "", without_urls, flags=re.MULTILINE)
        without_sources = re.split(r"\n\s*Sources\s*\n", without_markdown, flags=re.IGNORECASE)[0]
        sentences = re.split(r"(?<=[.!?])\s+", without_sources.replace("\n", " ").strip())
        return " ".join(sentence for sentence in sentences if sentence)[:900]
