from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.core.config.settings import settings
from app.models.desktop import DesktopAuthCode, DesktopDevice, DesktopRefreshSession
from app.models.user import User
from app.schemas.desktop_cloud import DesktopAuthorizeRequest, DesktopDevicePayload, DesktopExchangeRequest


ACCESS_TOKEN_SECONDS = 3600
REFRESH_TOKEN_DAYS = 60
AUTH_CODE_SECONDS = 120


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def is_expired(value: datetime) -> bool:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value < utc_now()


def _secret() -> bytes:
    value = settings.jwt_secret or settings.encryption_master_key
    if not value:
        raise HTTPException(status_code=503, detail="Desktop auth signing secret is not configured")
    return value.encode("utf-8")


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def _b64decode(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode((value + padding).encode("ascii"))


def token_hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def pkce_challenge(verifier: str) -> str:
    return _b64url(hashlib.sha256(verifier.encode("ascii")).digest())


class DesktopAuthService:
    def __init__(self, db: Session):
        self.db = db

    def authorize(self, user: User, payload: DesktopAuthorizeRequest) -> dict[str, Any]:
        if payload.redirect_uri != "ceaser://auth/callback":
            raise HTTPException(status_code=400, detail="Invalid desktop redirect URI")
        code = f"dac_{secrets.token_urlsafe(32)}"
        record = DesktopAuthCode(
            user_id=user.id,
            code_hash=token_hash(code),
            state=payload.state,
            code_challenge=payload.code_challenge,
            code_challenge_method=payload.code_challenge_method,
            device_id=payload.device_id,
            device_name=payload.device_name,
            platform=payload.platform,
            app_version=payload.app_version,
            expires_at=utc_now() + timedelta(seconds=AUTH_CODE_SECONDS),
        )
        self.db.add(record)
        self.upsert_device(user, payload)
        self.db.commit()
        return {"code": code, "state": payload.state, "expires_in": AUTH_CODE_SECONDS}

    def exchange(self, payload: DesktopExchangeRequest) -> dict[str, Any]:
        record = self.db.query(DesktopAuthCode).filter(DesktopAuthCode.code_hash == token_hash(payload.code)).first()
        if not record:
            raise HTTPException(status_code=400, detail="Invalid desktop authorization code")
        if record.used_at:
            raise HTTPException(status_code=400, detail="Desktop authorization code was already used")
        if is_expired(record.expires_at):
            raise HTTPException(status_code=400, detail="Desktop authorization code expired")
        if record.code_challenge != pkce_challenge(payload.code_verifier):
            raise HTTPException(status_code=400, detail="Invalid PKCE verifier")
        if record.device_id != payload.device.device_id:
            raise HTTPException(status_code=400, detail="Desktop device mismatch")
        user = self.db.get(User, record.user_id)
        if not user:
            raise HTTPException(status_code=401, detail="User no longer exists")
        record.used_at = utc_now()
        self.upsert_device(user, payload.device)
        refresh_token = f"dtr_{secrets.token_urlsafe(48)}"
        self.db.add(
            DesktopRefreshSession(
                user_id=user.id,
                device_id=payload.device.device_id,
                token_hash=token_hash(refresh_token),
                expires_at=utc_now() + timedelta(days=REFRESH_TOKEN_DAYS),
                last_used_at=utc_now(),
            )
        )
        self.db.commit()
        return self._session_payload(user, payload.device.device_id, refresh_token)

    def refresh(self, refresh_token: str, device_id: str | None = None) -> dict[str, Any]:
        session = self.db.query(DesktopRefreshSession).filter(DesktopRefreshSession.token_hash == token_hash(refresh_token)).first()
        if not session or session.revoked_at:
            raise HTTPException(status_code=401, detail="Desktop session revoked")
        if is_expired(session.expires_at):
            raise HTTPException(status_code=401, detail="Desktop session expired")
        if device_id and device_id != session.device_id:
            raise HTTPException(status_code=401, detail="Desktop device mismatch")
        device = self._device(session.user_id, session.device_id)
        if device and device.revoked_at:
            session.revoked_at = utc_now()
            self.db.commit()
            raise HTTPException(status_code=401, detail="Desktop device revoked")
        user = self.db.get(User, session.user_id)
        if not user:
            raise HTTPException(status_code=401, detail="User no longer exists")
        session.last_used_at = utc_now()
        if device:
            device.last_seen_at = utc_now()
        self.db.commit()
        return self._session_payload(user, session.device_id, refresh_token)

    def revoke(self, user: User, refresh_token: str | None = None, device_id: str | None = None) -> None:
        now = utc_now()
        query = self.db.query(DesktopRefreshSession).filter(DesktopRefreshSession.user_id == user.id)
        if refresh_token:
            query = query.filter(DesktopRefreshSession.token_hash == token_hash(refresh_token))
        if device_id:
            query = query.filter(DesktopRefreshSession.device_id == device_id)
        for session in query.all():
            session.revoked_at = now
        if device_id:
            device = self._device(user.id, device_id)
            if device:
                device.revoked_at = now
        self.db.commit()

    def upsert_device(self, user: User, payload: DesktopDevicePayload) -> DesktopDevice:
        now = utc_now()
        device = self._device(user.id, payload.device_id)
        if not device:
            device = DesktopDevice(user_id=user.id, device_id=payload.device_id, device_name=payload.device_name or "CEASER Desktop")
            self.db.add(device)
        device.device_name = payload.device_name or device.device_name
        device.platform = payload.platform
        device.app_version = payload.app_version
        device.last_seen_at = now
        device.revoked_at = None
        self.db.flush()
        return device

    def list_devices(self, user: User) -> list[DesktopDevice]:
        return self.db.query(DesktopDevice).filter(DesktopDevice.user_id == user.id).order_by(DesktopDevice.last_seen_at.desc().nullslast()).all()

    def _device(self, user_id: str, device_id: str) -> DesktopDevice | None:
        return self.db.query(DesktopDevice).filter(DesktopDevice.user_id == user_id, DesktopDevice.device_id == device_id).first()

    def _session_payload(self, user: User, device_id: str, refresh_token: str) -> dict[str, Any]:
        return {
            "access_token": create_desktop_access_token(user, device_id),
            "refresh_token": refresh_token,
            "expires_in": ACCESS_TOKEN_SECONDS,
            "token_type": "bearer",
            "user": {"id": user.id, "email": user.email},
        }


def create_desktop_access_token(user: User, device_id: str) -> str:
    now = int(utc_now().timestamp())
    payload = {
        "typ": "desktop_access",
        "sub": user.id,
        "email": user.email,
        "device_id": device_id,
        "iat": now,
        "exp": now + ACCESS_TOKEN_SECONDS,
    }
    body = _b64url(json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8"))
    sig = _b64url(hmac.new(_secret(), body.encode("ascii"), hashlib.sha256).digest())
    return f"cdat.{body}.{sig}"


def verify_desktop_access_token(token: str) -> dict[str, Any] | None:
    if not token.startswith("cdat."):
        return None
    try:
        _, body, sig = token.split(".", 2)
        expected = _b64url(hmac.new(_secret(), body.encode("ascii"), hashlib.sha256).digest())
        if not hmac.compare_digest(sig, expected):
            return None
        payload = json.loads(_b64decode(body).decode("utf-8"))
        if payload.get("typ") != "desktop_access" or int(payload.get("exp") or 0) < int(utc_now().timestamp()):
            return None
        return payload
    except Exception:
        return None
