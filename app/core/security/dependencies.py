from typing import Annotated
from time import monotonic
from threading import Lock
import logging

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.config.settings import settings
from app.core.database.session import get_db
from app.core.security.supabase_auth import supabase_auth
from app.models.user import User
from app.models.desktop import DesktopDevice
from app.repositories.user_repository import UserRepository
from app.services.desktop_auth_service import verify_desktop_access_token


_AUTH_CACHE_TTL_SECONDS = 300.0
_AUTH_CACHE: dict[str, tuple[float, dict[str, str]]] = {}
_AUTH_CACHE_LOCK = Lock()
logger = logging.getLogger(__name__)


def _cached_supabase_user(access_token: str) -> dict[str, str] | None:
    now = monotonic()
    with _AUTH_CACHE_LOCK:
        cached = _AUTH_CACHE.get(access_token)
        if not cached:
            return None
        expires_at, user = cached
        if expires_at <= now:
            _AUTH_CACHE.pop(access_token, None)
            return None
        return user


def _store_cached_supabase_user(access_token: str, user: dict[str, str]) -> None:
    with _AUTH_CACHE_LOCK:
        _AUTH_CACHE[access_token] = (monotonic() + _AUTH_CACHE_TTL_SECONDS, user)


async def get_current_user(
    db: Annotated[Session, Depends(get_db)],
    authorization: Annotated[str | None, Header()] = None,
) -> User:
    auth_started = monotonic()
    logger.info("ceaser_auth_stage stage=auth_started")
    if settings.dev_auth_bypass:
        repo = UserRepository(db)
        try:
            user = repo.get_or_create(email="dev@ceaser.local", user_id="00000000-0000-4000-8000-000000000001")
            db.commit()
            db.refresh(user)
            logger.info("ceaser_auth_stage stage=auth_complete mode=dev duration_ms=%.2f", (monotonic() - auth_started) * 1000)
            return user
        except (SQLAlchemyError, Exception) as exc:
            db.rollback()
            raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="CEASER account setup is temporarily unavailable.") from exc

    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing bearer token")

    token = authorization.split(" ", 1)[1]
    desktop_payload = verify_desktop_access_token(token)
    if desktop_payload:
        user = db.get(User, desktop_payload.get("sub"))
        if not user:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid desktop session")
        device_id = desktop_payload.get("device_id")
        if device_id:
            device = db.query(DesktopDevice).filter(DesktopDevice.user_id == user.id, DesktopDevice.device_id == device_id).first()
            if device and device.revoked_at:
                raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Desktop device revoked")
        logger.info("ceaser_auth_stage stage=auth_complete mode=desktop duration_ms=%.2f", (monotonic() - auth_started) * 1000)
        return user
    try:
        supabase_user = _cached_supabase_user(token)
        if supabase_user is None:
            remote_started = monotonic()
            supabase_user = await supabase_auth.get_user(token)
            _store_cached_supabase_user(token, {"email": supabase_user.get("email") or "", "id": supabase_user.get("id") or ""})
            logger.info("ceaser_auth_stage stage=supabase_remote duration_ms=%.2f", (monotonic() - remote_started) * 1000)
        else:
            logger.info("ceaser_auth_stage stage=supabase_cache_hit")
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid session") from exc

    email = supabase_user.get("email")
    user_id = supabase_user.get("id")
    if not email or not user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid Supabase user")

    repo = UserRepository(db)
    try:
        user = repo.get_or_create(email=email, user_id=user_id)
        db.commit()
        db.refresh(user)
        logger.info("ceaser_auth_stage stage=auth_complete mode=supabase duration_ms=%.2f", (monotonic() - auth_started) * 1000)
        return user
    except (SQLAlchemyError, Exception) as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="CEASER account setup is temporarily unavailable.") from exc
