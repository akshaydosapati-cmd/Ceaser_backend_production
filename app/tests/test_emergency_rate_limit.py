from app.core.rate_limiter import BoundedRateLimiter
from app.api.auth.routes import enforce_auth_rate_limit
from fastapi import HTTPException
from starlette.requests import Request


def test_request_rate_limit_and_retry_after() -> None:
    limiter = BoundedRateLimiter(max_keys=8, ttl_seconds=60)
    assert all(limiter.check("chat", "user-1", limit=10, window_seconds=60).allowed for _ in range(10))
    blocked = limiter.check("chat", "user-1", limit=10, window_seconds=60)
    assert blocked.allowed is False
    assert blocked.retry_after > 0


def test_concurrency_releases_and_storage_is_bounded() -> None:
    limiter = BoundedRateLimiter(max_keys=4, ttl_seconds=60)
    assert all(limiter.acquire("chat", "user-1", limit=3).allowed for _ in range(3))
    assert limiter.acquire("chat", "user-1", limit=3).allowed is False
    limiter.release("chat", "user-1")
    assert limiter.acquire("chat", "user-1", limit=3).allowed is True
    for index in range(20):
        limiter.check("auth", f"198.51.100.{index}", limit=10, window_seconds=60)
    assert len(limiter._requests) <= 4
    assert all("198.51.100" not in key and "user-1" not in key for key in limiter._requests)


def test_auth_limit_returns_structured_429(monkeypatch) -> None:
    limiter = BoundedRateLimiter(max_keys=8, ttl_seconds=60)
    monkeypatch.setattr("app.api.auth.routes.rate_limiter", limiter)
    request = Request({"type": "http", "headers": [], "client": ("203.0.113.10", 1234)})
    for _ in range(10):
        enforce_auth_rate_limit(request)
    try:
        enforce_auth_rate_limit(request)
        raise AssertionError("expected auth rate limit")
    except HTTPException as exc:
        assert exc.status_code == 429
        assert exc.detail["code"] == "rate_limited"
        assert int(exc.headers["Retry-After"]) > 0
