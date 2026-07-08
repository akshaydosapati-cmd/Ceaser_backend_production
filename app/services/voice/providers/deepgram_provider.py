from __future__ import annotations

import httpx

from app.core.config.settings import settings
from app.services.voice.speech_to_text import STTProvider


class DeepgramProvider(STTProvider):
    def __init__(self, api_key: str | None = None):
        self.api_key = api_key or settings.deepgram_api_key

    def transcribe(self, audio: bytes, *, content_type: str, language: str) -> str:
        if not self.api_key:
            raise RuntimeError("DEEPGRAM_API_KEY is not configured.")
        params = {"model": "nova-3", "smart_format": "true", "language": language}
        headers = {"Authorization": f"Token {self.api_key}", "Content-Type": content_type}
        with httpx.Client(timeout=45) as client:
            response = client.post("https://api.deepgram.com/v1/listen", params=params, headers=headers, content=audio)
            response.raise_for_status()
        data = response.json()
        channels = data.get("results", {}).get("channels", [])
        alternatives = channels[0].get("alternatives", []) if channels else []
        transcript = alternatives[0].get("transcript", "") if alternatives else ""
        return transcript.strip()

    def stream_transcribe(self, audio: bytes, *, content_type: str, language: str) -> str:
        return self.transcribe(audio, content_type=content_type, language=language)
