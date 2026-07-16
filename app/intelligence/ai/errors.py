from __future__ import annotations


class AIServiceUnavailableError(RuntimeError):
    public_message = "AI service is temporarily unavailable. Please try again later."

    def __init__(self, detail: str | None = None) -> None:
        super().__init__(self.public_message)
        self.detail = detail
