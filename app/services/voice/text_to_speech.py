from __future__ import annotations

from abc import ABC, abstractmethod


class TTSProvider(ABC):
    @abstractmethod
    def speak(self, text: str, *, voice_id: str | None = None) -> tuple[bytes, str]:
        raise NotImplementedError

    @abstractmethod
    def stream_speak(self, text: str, *, voice_id: str | None = None) -> tuple[bytes, str]:
        raise NotImplementedError
