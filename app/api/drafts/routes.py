from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database.session import get_db
from app.core.security.dependencies import get_current_user
from app.models.draft import Draft
from app.models.user import User
from app.schemas.draft import AgentWorkbenchRead, DraftCreate, DraftHistoryRead, DraftRead
from app.services.audit_service import AuditService
from app.services.drafts import DraftManager
from app.services.drafts.draft_storage import DraftStorage
from app.services.drafts.structured_draft_generator import DraftGenerationError
from app.services.document_generation.template_manager import TemplateManager

router = APIRouter(prefix="/drafts", tags=["drafts"])
agent_router = APIRouter(prefix="/agent-workbenches", tags=["agent-workbenches"])


@router.get("", response_model=list[DraftRead])
def list_drafts(user: Annotated[User, Depends(get_current_user)], db: Annotated[Session, Depends(get_db)], agent_id: str | None = None, status: str | None = None):
    return [_draft_read(draft) for draft in DraftStorage(db).list(user_id=user.id, agent_id=agent_id, status=status)]


@router.post("", response_model=DraftRead)
def create_draft(payload: DraftCreate, user: Annotated[User, Depends(get_current_user)], db: Annotated[Session, Depends(get_db)]):
    try:
        draft = DraftManager(db).create(user_id=user.id, prompt=payload.prompt, draft_type=payload.draft_type, agent_id=payload.agent_id, target_app=payload.target_app, requested_units=payload.requested_units)
    except DraftGenerationError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    AuditService(db).record(user_id=user.id, action="draft_created", resource_type="draft", resource_id=draft.id)
    return _draft_read(draft)


@router.post("/{draft_id}/{action}", response_model=DraftRead)
def transition_draft(draft_id: str, action: str, user: Annotated[User, Depends(get_current_user)], db: Annotated[Session, Depends(get_db)]):
    if action not in {"regenerated", "approved", "archived"}:
        raise HTTPException(status_code=400, detail="Unsupported draft action.")
    draft = db.get(Draft, draft_id)
    if not draft or draft.user_id != user.id:
        raise HTTPException(status_code=404, detail="Draft not found.")
    try:
        updated = DraftManager(db).transition(draft=draft, user_id=user.id, action=action)
    except DraftGenerationError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    AuditService(db).record(user_id=user.id, action=f"draft_{action}", resource_type="draft", resource_id=draft.id)
    return _draft_read(updated)


@router.delete("/{draft_id}")
def delete_draft(draft_id: str, user: Annotated[User, Depends(get_current_user)], db: Annotated[Session, Depends(get_db)]):
    draft = db.get(Draft, draft_id)
    if not draft or draft.user_id != user.id:
        raise HTTPException(status_code=404, detail="Draft not found.")
    AuditService(db).record(user_id=user.id, action="draft_deleted", resource_type="draft", resource_id=draft.id)
    db.delete(draft)
    db.commit()
    return {"status": "deleted", "id": draft_id}


@agent_router.get("/{agent_id}", response_model=AgentWorkbenchRead)
def get_agent_workbench(agent_id: str, user: Annotated[User, Depends(get_current_user)], db: Annotated[Session, Depends(get_db)]):
    storage = DraftStorage(db)
    drafts = storage.list(user_id=user.id, agent_id=agent_id)
    activity = storage.list_history(user_id=user.id, agent_id=agent_id)
    active = [draft for draft in drafts if draft.status not in {"approved", "archived"}]
    approved = [draft for draft in drafts if draft.status == "approved"]
    return {
        "agent_id": agent_id,
        "kpis": {
            "active_drafts": len(active),
            "completed_drafts": len(approved),
            "reports_generated": len(drafts),
            "strategies_created": len([draft for draft in drafts if draft.draft_type in {"business_plan", "presentation"}]),
        },
        "quick_actions": _quick_actions(agent_id),
        "templates": [template.model_dump() for template in TemplateManager().list(agent_id=agent_id)],
        "drafts": [_draft_read(draft) for draft in drafts],
        "activity": [_history_read(item) for item in activity],
    }


def _quick_actions(agent_id: str) -> list[str]:
    return {
        "zeus": ["Create Business Plan", "Create Pitch Deck", "Create SWOT Analysis", "Create Revenue Strategy", "Market Analysis"],
        "nova": ["Create Research Report", "Create Industry Analysis", "Create Competitor Report", "Create Market Overview"],
        "atlas": ["Create Architecture Report", "Create Technical Design", "Create Planning Document", "Create API Documentation"],
        "friday": ["Create Content Calendar", "Create Campaign Plan", "Create Social Strategy", "Create Content Pack"],
        "alex": ["Create Study Plan", "Create Goal Plan", "Create Learning Roadmap", "Create Travel Plan"],
        "bolt": ["Create Execution Plan", "Create Project Tracker", "Create Task Breakdown", "Create Workflow"],
    }.get(agent_id, ["Create Draft"])


def _draft_read(draft: Draft) -> DraftRead:
    return DraftRead(
        id=draft.id,
        user_id=draft.user_id,
        agent_id=draft.agent_id,
        title=draft.title,
        draft_type=draft.draft_type,
        status=draft.status,
        progress=draft.progress,
        target_app=draft.target_app,
        requested_units=draft.requested_units,
        source_prompt=draft.source_prompt,
        content=draft.content,
        created_at=draft.created_at,
    )


def _history_read(item) -> DraftHistoryRead:
    return DraftHistoryRead(
        id=item.id,
        draft_id=item.draft_id,
        user_id=item.user_id,
        agent_id=item.agent_id,
        action=item.action,
        detail=item.detail,
        created_at=item.created_at,
    )
