from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class LLMProvider(ABC):
    @abstractmethod
    def generate_response(self, message: str, context: dict[str, Any]) -> str:
        raise NotImplementedError
