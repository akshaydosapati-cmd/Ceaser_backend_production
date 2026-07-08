from __future__ import annotations

from sqlalchemy.orm import Session

from app.models.workflow import WorkflowRun, WorkflowStep
from app.services.audit_service import AuditService
from app.services.workflows.workflow_templates import WorkflowTemplateRegistry


class WorkflowManager:
    def __init__(self, db: Session):
        self.db = db
        self.templates = WorkflowTemplateRegistry()

    def templates_list(self) -> list[dict]:
        return [template.model_dump() for template in self.templates.list()]

    def list(self, user_id: str) -> list[WorkflowRun]:
        return self.db.query(WorkflowRun).filter(WorkflowRun.user_id == user_id).order_by(WorkflowRun.created_at.desc()).all()

    def get(self, workflow_id: str, user_id: str) -> WorkflowRun | None:
        return self.db.query(WorkflowRun).filter(WorkflowRun.id == workflow_id, WorkflowRun.user_id == user_id).first()

    def create(self, *, user_id: str, workflow_type: str, agents: list[str], metadata: dict | None = None) -> WorkflowRun:
        run = WorkflowRun(user_id=user_id, workflow_type=workflow_type, status="pending", metadata_json=metadata or {})
        self.db.add(run)
        self.db.flush()
        for agent in agents:
            run.steps.append(WorkflowStep(workflow_id=run.id, agent_name=agent, status="pending", metadata_json={}))
        AuditService(self.db).record(user_id=user_id, action="workflow_created", resource_type="workflow", resource_id=run.id, metadata={"workflow_type": workflow_type, "agents": agents}, commit=False)
        self.db.flush()
        return run

    def steps(self, run: WorkflowRun) -> list[WorkflowStep]:
        return self.db.query(WorkflowStep).filter(WorkflowStep.workflow_id == run.id).all()

    def cancel(self, run: WorkflowRun) -> WorkflowRun:
        run.status = "cancelled"
        AuditService(self.db).record(user_id=run.user_id, action="workflow_cancelled", resource_type="workflow", resource_id=run.id, commit=False)
        self.db.commit()
        self.db.refresh(run)
        return run
