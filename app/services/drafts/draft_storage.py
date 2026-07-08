from __future__ import annotations

from sqlalchemy.orm import Session

from app.models.draft import Draft, DraftHistory
from app.services.drafts.schemas import DraftContent


class DraftStorage:
    def __init__(self, db: Session):
        self.db = db

    def create(self, *, user_id: str, agent_id: str, draft_type: str, prompt: str, content: DraftContent, target_app: str = "keep_as_draft", requested_units: int = 8) -> Draft:
        draft = Draft(
            user_id=user_id,
            agent_id=agent_id,
            title=content.title,
            draft_type=draft_type,
            status="draft_ready",
            progress=100,
            target_app=target_app,
            requested_units=requested_units,
        )
        draft.source_prompt = prompt
        draft.content = content.model_dump()
        self.db.add(draft)
        self.db.flush()
        self.history(draft=draft, user_id=user_id, action="created", detail=f"Created {content.title}")
        return draft

    def history(self, *, draft: Draft, user_id: str, action: str, detail: str) -> DraftHistory:
        item = DraftHistory(draft_id=draft.id, user_id=user_id, agent_id=draft.agent_id, action=action)
        item.detail = detail
        self.db.add(item)
        self.db.flush()
        return item

    def list(self, *, user_id: str | None = None, agent_id: str | None = None, status: str | None = None) -> list[Draft]:
        query = self.db.query(Draft)
        if user_id:
            query = query.filter(Draft.user_id == user_id)
        if agent_id:
            query = query.filter(Draft.agent_id == agent_id)
        if status:
            query = query.filter(Draft.status == status)
        return query.order_by(Draft.created_at.desc()).all()

    def list_history(self, *, user_id: str | None = None, agent_id: str | None = None) -> list[DraftHistory]:
        query = self.db.query(DraftHistory)
        if user_id:
            query = query.filter(DraftHistory.user_id == user_id)
        if agent_id:
            query = query.filter(DraftHistory.agent_id == agent_id)
        return query.order_by(DraftHistory.created_at.desc()).limit(100).all()
