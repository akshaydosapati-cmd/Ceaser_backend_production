from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.database.session import get_db
from app.core.security.dependencies import get_current_user
from app.models.user import User
from app.services.audit_service import AuditService
from app.services.live import LiveService
from app.services.live.schemas import LiveNewsBrief, LiveStatus, LiveWeatherReport

router = APIRouter(prefix="/live", tags=["live"])


@router.get("/status", response_model=LiveStatus)
def live_status(user: Annotated[User, Depends(get_current_user)]) -> LiveStatus:
    return LiveService().status()


@router.get("/news/latest", response_model=LiveNewsBrief)
def latest_news(user: Annotated[User, Depends(get_current_user)], db: Annotated[Session, Depends(get_db)]) -> LiveNewsBrief:
    result = LiveService().latest_news()
    AuditService(db).record(user_id=user.id, action="live_news_requested", resource_type="live", metadata={"mode": "latest"})
    return result


@router.get("/news/search", response_model=LiveNewsBrief)
def search_news(
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
    q: Annotated[str, Query(min_length=1, max_length=160)],
) -> LiveNewsBrief:
    result = LiveService().search_news(q)
    AuditService(db).record(user_id=user.id, action="live_news_requested", resource_type="live", metadata={"mode": "search"})
    return result


@router.get("/news/category/{category}", response_model=LiveNewsBrief)
def category_news(
    category: str,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> LiveNewsBrief:
    result = LiveService().category_news(category)
    AuditService(db).record(user_id=user.id, action="live_news_requested", resource_type="live", metadata={"mode": "category", "category": category})
    return result


@router.get("/weather/current", response_model=LiveWeatherReport)
def current_weather(
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
    location: str | None = None,
) -> LiveWeatherReport:
    result = LiveService().current_weather(location)
    AuditService(db).record(user_id=user.id, action="live_weather_requested", resource_type="live", metadata={"location": result.location})
    return result
