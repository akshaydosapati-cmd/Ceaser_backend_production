from __future__ import annotations

import httpx

from app.core.config.settings import settings
from app.services.voice.text_to_speech import TTSProvider


class ElevenLabsProvider(TTSProvider):
    def __init__(self, api_key: str | None = None, voice_id: str | None = None):
        self.api_key = api_key or settings.elevenlabs_api_key
        self.voice_id = voice_id or settings.elevenlabs_voice_id

    def speak(self, text: str, *, voice_id: str | None = None) -> tuple[bytes, str]:
        if not self.api_key:
            raise RuntimeError("ELEVENLABS_API_KEY is not configured.")
        selected_voice = voice_id or self.voice_id
        if not selected_voice:
            raise RuntimeError("ELEVENLABS_VOICE_ID is not configured.")
        payload = {
            "text": text,
            "model_id": "eleven_multilingual_v2",
            "voice_settings": {"stability": 0.45, "similarity_boost": 0.75},
        }
        headers = {"xi-api-key": self.api_key, "Accept": "audio/mpeg", "Content-Type": "application/json"}
        url = f"https://api.elevenlabs.io/v1/text-to-speech/{selected_voice}/stream"
        with httpx.Client(timeout=60) as client:
            response = client.post(url, headers=headers, json=payload)
            response.raise_for_status()
        return response.content, response.headers.get("content-type", "audio/mpeg")

    def stream_speak(self, text: str, *, voice_id: str | None = None) -> tuple[bytes, str]:
        return self.speak(text, voice_id=voice_id)
