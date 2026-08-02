from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.config.settings import settings
from app.core.database.session import get_db
from app.core.security.dependencies import get_current_user
from app.models.admin import DownloadEvent
from app.models.user import User


router = APIRouter(prefix="/admin", tags=["admin"])


class AdminMeResponse(BaseModel):
    is_admin: bool
    email: str


class DownloadTrackRequest(BaseModel):
    source: str = Field(default="website", max_length=80)
    platform: str = Field(default="windows", max_length=80)
    version: str | None = Field(default=None, max_length=80)


def _require_admin(user: User) -> User:
    if user.email.lower() not in settings.admin_emails:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required")
    return user


def require_admin_user(user: Annotated[User, Depends(get_current_user)]) -> User:
    return _require_admin(user)


def _scalar(db: Session, statement: str, params: dict | None = None, default: int | float = 0) -> int | float:
    try:
        value = db.execute(text(statement), params or {}).scalar()
        return value if value is not None else default
    except Exception:
        db.rollback()
        return default


def _rows(db: Session, statement: str, params: dict | None = None) -> list[dict]:
    try:
        return [dict(row._mapping) for row in db.execute(text(statement), params or {}).all()]
    except Exception:
        db.rollback()
        return []


def _client_ip_hash(request: Request) -> str | None:
    raw_ip = request.headers.get("x-forwarded-for", "").split(",", 1)[0].strip() or (request.client.host if request.client else "")
    if not raw_ip:
        return None
    salt = settings.jwt_secret or settings.encryption_master_key or "ceaser-admin"
    return hashlib.sha256(f"{salt}:{raw_ip}".encode("utf-8")).hexdigest()


@router.get("/me", response_model=AdminMeResponse)
def admin_me(user: Annotated[User, Depends(get_current_user)]) -> AdminMeResponse:
    return AdminMeResponse(is_admin=user.email.lower() in settings.admin_emails, email=user.email)


@router.post("/downloads/track")
def track_download(payload: DownloadTrackRequest, request: Request, db: Annotated[Session, Depends(get_db)]) -> dict[str, str]:
    event = DownloadEvent(
        source=payload.source.strip().lower() or "website",
        platform=payload.platform.strip().lower() or "windows",
        version=(payload.version or "").strip() or None,
        user_agent=(request.headers.get("user-agent") or "")[:500] or None,
        ip_hash=_client_ip_hash(request),
    )
    db.add(event)
    db.commit()
    return {"status": "ok"}


@router.get("/overview")
def admin_overview(
    user: Annotated[User, Depends(require_admin_user)],
    db: Annotated[Session, Depends(get_db)],
) -> dict:
    now = datetime.now(timezone.utc).isoformat()
    return {
        "generated_at": now,
        "admin": {"email": user.email},
        "totals": {
            "users": int(_scalar(db, "select count(*) from users")),
            "new_users_7d": int(_scalar(db, "select count(*) from users where created_at >= now() - interval '7 days'")),
            "downloads": int(_scalar(db, "select count(*) from download_events")),
            "downloads_24h": int(_scalar(db, "select count(*) from download_events where created_at >= now() - interval '24 hours'")),
            "waitlist": int(_scalar(db, "select count(*) from launch_waitlist")),
            "projects": int(_scalar(db, "select count(*) from projects")),
            "files": int(_scalar(db, "select count(*) from files")),
            "conversations": int(_scalar(db, "select count(*) from conversations")),
            "messages": int(_scalar(db, "select count(*) from messages")),
            "active_subscriptions": int(_scalar(db, "select count(*) from subscriptions where status in ('active','authenticated')")),
            "payments": int(_scalar(db, "select count(*) from billing_payments where status in ('captured','paid','authorized')")),
            "revenue_paise": int(_scalar(db, "select coalesce(sum(amount), 0) from billing_payments where status in ('captured','paid','authorized')")),
        },
        "downloads_by_source": _rows(
            db,
            "select source, platform, count(*) as count from download_events group by source, platform order by count desc limit 12",
        ),
        "plans": _rows(
            db,
            """
            select p.code, p.name, count(s.id) as subscriptions
            from plans p
            left join subscriptions s on s.plan_id = p.id and s.status in ('active','authenticated')
            group by p.code, p.name
            order by subscriptions desc, p.code
            """,
        ),
        "recent_users": _rows(
            db,
            "select id, email, created_at from users order by created_at desc limit 8",
        ),
        "recent_downloads": _rows(
            db,
            "select source, platform, version, created_at from download_events order by created_at desc limit 10",
        ),
        "recent_payments": _rows(
            db,
            """
            select bp.provider_payment_id, bp.amount, bp.currency, bp.status, bp.created_at, u.email
            from billing_payments bp
            left join users u on u.id = bp.user_id
            order by bp.created_at desc
            limit 8
            """,
        ),
        "usage_7d": _rows(
            db,
            """
            select action_type, coalesce(sum(quantity), 0) as quantity, coalesce(sum(input_tokens + output_tokens + embedding_tokens), 0) as tokens
            from usage_ledger
            where created_at >= now() - interval '7 days'
            group by action_type
            order by quantity desc
            limit 12
            """,
        ),
    }
