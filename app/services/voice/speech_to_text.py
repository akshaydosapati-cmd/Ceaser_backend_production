from __future__ import annotations

from abc import ABC, abstractmethod


class STTProvider(ABC):
    @abstractmethod
    def transcribe(self, audio: bytes, *, content_type: str, language: str) -> str:
        raise NotImplementedError

    @abstractmethod
    def stream_transcribe(self, audio: bytes, *, content_type: str, language: str) -> str:
        raise NotImplementedError
