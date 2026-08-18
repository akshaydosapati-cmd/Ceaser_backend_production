from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.database.session import get_db
from app.core.security.dependencies import get_current_user
from app.engines.research_engine import ResearchEngine
from app.engines.research_engine.schemas import ResearchRequest, ResearchResult
from app.models.user import User
from app.services.audit_service import AuditService
from app.services.credit_service import CreditService, InsufficientCreditsError
from fastapi import HTTPException
from uuid import uuid4

router = APIRouter(prefix="/research", tags=["research"])


@router.post("", response_model=ResearchResult)
def research(payload: ResearchRequest, user: Annotated[User, Depends(get_current_user)], db: Annotated[Session, Depends(get_db)]):
    request_id = f"research:{uuid4().hex}"
    credits = CreditService(db)
    try:
        reservation = credits.reserve(user.id, request_id, "research")
    except InsufficientCreditsError as exc:
        raise HTTPException(status_code=402, detail="Insufficient CEASER credits.") from exc
    try:
        result = ResearchEngine().research(payload.query)
        credits.settle(user.id, request_id, reservation.estimated_credits, meaningful_output=bool(result.sources))
    except Exception:
        credits.release(user.id, request_id)
        raise
    AuditService(db).record(
        user_id=user.id,
        action="research_requested",
        resource_type="research",
        metadata={"source_count": len(result.sources)},
    )
    return result
