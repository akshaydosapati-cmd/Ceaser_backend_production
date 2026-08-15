import logging
from typing import Annotated
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.database.session import get_db
from app.services.email.resend_service import send_test_email

router = APIRouter(prefix="/api/v1/waitlist", tags=["waitlist"])
logger = logging.getLogger(__name__)


class WaitlistJoinRequest(BaseModel):
    email: EmailStr


class WaitlistJoinResponse(BaseModel):
    success: bool
    message: str


@router.post("", response_model=WaitlistJoinResponse)
def join_waitlist(payload: WaitlistJoinRequest, db: Annotated[Session, Depends(get_db)]) -> WaitlistJoinResponse:
    email = str(payload.email).strip().lower()

    existing = db.execute(
        text("SELECT 1 FROM launch_waitlist WHERE lower(email) = lower(:email) LIMIT 1"),
        {"email": email},
    ).scalar_one_or_none()

    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="You're already on the CEASER Launch List 🎉\n\nWe'll notify you as soon as CEASER launches.",
        )

    try:
        db.execute(
            text(
                """
                INSERT INTO launch_waitlist (id, email, name, source, status, created_at, updated_at)
                VALUES (:id, :email, NULL, 'website', 'active', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                """
            ),
            {"id": str(uuid4()), "email": email},
        )
        db.commit()
    except Exception:
        db.rollback()
        raise

    try:
        send_test_email(email)
    except Exception:
        logger.exception("Failed to send welcome email to %s", email)

    return WaitlistJoinResponse(success=True, message="Successfully joined the launch list.")
