from __future__ import annotations

import time
from typing import Any


class TTLCache:
    def __init__(self) -> None:
        self._items: dict[str, tuple[float, Any]] = {}

    def get(self, key: str) -> Any | None:
        item = self._items.get(key)
        if not item:
            return None
        expires_at, value = item
        if expires_at <= time.time():
            self._items.pop(key, None)
            return None
        return value

    def set(self, key: str, value: Any, ttl_seconds: int) -> None:
        self._items[key] = (time.time() + ttl_seconds, value)


ttl_cache = TTLCache()
