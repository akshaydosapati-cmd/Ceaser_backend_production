from __future__ import annotations

from sqlalchemy.orm import Session

from app.models.generated_document import AgentActivity, GeneratedDocument


class ExportManager:
    def __init__(self, db: Session):
        self.db = db

    def record_generated(self, *, file_id: str, user_id: str, agent_id: str, template_id: str, export_format: str, prompt: str) -> GeneratedDocument:
        record = GeneratedDocument(
            file_id=file_id,
            user_id=user_id,
            agent_id=agent_id,
            template_id=template_id,
            generated_by=agent_id,
            export_format=export_format,
            version=1,
        )
        record.source_prompt = prompt
        self.db.add(record)
        self.activity(user_id=user_id, file_id=file_id, agent_id=agent_id, action="generated", detail=f"Generated {export_format.upper()} using {template_id}")
        self.db.flush()
        return record

    def activity(self, *, user_id: str, agent_id: str, action: str, detail: str, file_id: str | None = None) -> AgentActivity:
        activity = AgentActivity(user_id=user_id, file_id=file_id, agent_id=agent_id, action=action)
        activity.detail = detail
        self.db.add(activity)
        self.db.flush()
        return activity

    def list_generated(self, user_id: str | None = None, agent_id: str | None = None) -> list[GeneratedDocument]:
        query = self.db.query(GeneratedDocument)
        if user_id:
            query = query.filter(GeneratedDocument.user_id == user_id)
        if agent_id:
            query = query.filter(GeneratedDocument.agent_id == agent_id)
        return query.order_by(GeneratedDocument.created_at.desc()).all()

    def list_activity(self, user_id: str | None = None, agent_id: str | None = None) -> list[AgentActivity]:
        query = self.db.query(AgentActivity)
        if user_id:
            query = query.filter(AgentActivity.user_id == user_id)
        if agent_id:
            query = query.filter(AgentActivity.agent_id == agent_id)
        return query.order_by(AgentActivity.created_at.desc()).limit(100).all()
