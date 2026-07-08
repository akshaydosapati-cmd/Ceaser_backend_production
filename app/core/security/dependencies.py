from typing import Annotated

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.config.settings import settings
from app.core.database.session import get_db
from app.core.security.supabase_auth import supabase_auth
from app.models.user import User
from app.repositories.user_repository import UserRepository
from app.services.agent_service import AgentService


def ensure_dev_user_agents(db: Session, user_id: str) -> None:
    AgentService(db).ensure_default_agents(user_id)


async def get_current_user(
    db: Annotated[Session, Depends(get_db)],
    authorization: Annotated[str | None, Header()] = None,
) -> User:
    if settings.dev_auth_bypass:
        repo = UserRepository(db)
        try:
            user = repo.get_or_create(email="dev@ceaser.local", user_id="00000000-0000-4000-8000-000000000001")
            db.commit()
            db.refresh(user)
            ensure_dev_user_agents(db, user.id)
            return user
        except (SQLAlchemyError, Exception) as exc:
            db.rollback()
            raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="CEASER account setup is temporarily unavailable.") from exc

    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing bearer token")

    token = authorization.split(" ", 1)[1]
    try:
        supabase_user = await supabase_auth.get_user(token)
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
        AgentService(db).ensure_default_agents(user.id)
        return user
    except (SQLAlchemyError, Exception) as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="CEASER account setup is temporarily unavailable.") from exc
