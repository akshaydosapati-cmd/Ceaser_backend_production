from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.database.session import get_db
from app.core.security.dependencies import get_current_user
from app.engines.research_engine import ResearchEngine
from app.engines.research_engine.schemas import ResearchRequest, ResearchResult
from app.models.user import User
from app.services.audit_service import AuditService

router = APIRouter(prefix="/research", tags=["research"])


@router.post("", response_model=ResearchResult)
def research(payload: ResearchRequest, user: Annotated[User, Depends(get_current_user)], db: Annotated[Session, Depends(get_db)]):
    result = ResearchEngine().research(payload.query)
    AuditService(db).record(
        user_id=user.id,
        action="research_requested",
        resource_type="research",
        metadata={"source_count": len(result.sources)},
    )
    return result
