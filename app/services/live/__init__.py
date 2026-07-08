from __future__ import annotations

from typing import Any

__all__ = ["LiveService"]


def __getattr__(name: str) -> Any:
    if name == "LiveService":
        from app.services.live.live_service import LiveService

        return LiveService
    raise AttributeError(name)
