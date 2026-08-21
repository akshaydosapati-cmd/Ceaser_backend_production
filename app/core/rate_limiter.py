from __future__ import annotations

from collections import OrderedDict, deque
from dataclasses import dataclass
import hashlib
import math
import secrets
from threading import Lock
from time import monotonic


@dataclass(frozen=True)
class LimitDecision:
    allowed: bool
    retry_after: int = 0


class BoundedRateLimiter:
    """Small process-local limiter with hashed identities and bounded storage."""

    def __init__(self, *, max_keys: int = 10_000, ttl_seconds: int = 600) -> None:
        self.max_keys = max_keys
        self.ttl_seconds = ttl_seconds
        self._salt = secrets.token_bytes(16)
        self._requests: OrderedDict[str, deque[float]] = OrderedDict()
        self._active: OrderedDict[str, tuple[int, float]] = OrderedDict()
        self._lock = Lock()
        self._last_cleanup = 0.0

    def check(self, namespace: str, identity: str, *, limit: int, window_seconds: int) -> LimitDecision:
        now = monotonic()
        key = self._key(namespace, identity)
        with self._lock:
            self._cleanup(now)
            timestamps = self._requests.get(key)
            if timestamps is None:
                self._ensure_capacity(self._requests)
                timestamps = deque()
                self._requests[key] = timestamps
            else:
                self._requests.move_to_end(key)
            cutoff = now - window_seconds
            while timestamps and timestamps[0] <= cutoff:
                timestamps.popleft()
            if len(timestamps) >= limit:
                return LimitDecision(False, max(1, math.ceil(window_seconds - (now - timestamps[0]))))
            timestamps.append(now)
            return LimitDecision(True)

    def acquire(self, namespace: str, identity: str, *, limit: int) -> LimitDecision:
        now = monotonic()
        key = self._key(namespace, identity)
        with self._lock:
            self._cleanup(now)
            active, _ = self._active.get(key, (0, now))
            if active >= limit:
                return LimitDecision(False, 1)
            self._ensure_capacity(self._active)
            self._active[key] = (active + 1, now)
            self._active.move_to_end(key)
            return LimitDecision(True)

    def release(self, namespace: str, identity: str) -> None:
        key = self._key(namespace, identity)
        now = monotonic()
        with self._lock:
            active, _ = self._active.get(key, (0, now))
            if active <= 1:
                self._active.pop(key, None)
            else:
                self._active[key] = (active - 1, now)
                self._active.move_to_end(key)

    def _key(self, namespace: str, identity: str) -> str:
        value = f"{namespace}:{identity}".encode("utf-8", errors="ignore")
        return hashlib.blake2b(value, key=self._salt, digest_size=16).hexdigest()

    def _cleanup(self, now: float) -> None:
        if now - self._last_cleanup < 30:
            return
        cutoff = now - self.ttl_seconds
        stale = [key for key, timestamps in self._requests.items() if not timestamps or timestamps[-1] < cutoff]
        for key in stale:
            self._requests.pop(key, None)
        self._last_cleanup = now

    def _ensure_capacity(self, store: OrderedDict) -> None:
        while len(store) >= self.max_keys:
            store.popitem(last=False)


rate_limiter = BoundedRateLimiter()
