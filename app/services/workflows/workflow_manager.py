from __future__ import annotations

from sqlalchemy.orm import Session

from app.models.workflow import WorkflowRun, WorkflowStep
from app.services.audit_service import AuditService
from app.services.workflows.workflow_templates import WorkflowTemplateRegistry
from app.services.workflows.schemas import GoalWorkflowPlan


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

    def create_goal_plan(self, plan: GoalWorkflowPlan) -> WorkflowRun:
        run = WorkflowRun(user_id=plan.goal.user_id, workflow_type="goal_workflow", status="pending", metadata_json={"goal_plan": plan.model_dump(mode="json"), "outputs": {}, "replan_count": 0})
        self.db.add(run)
        self.db.flush()
        for planned in plan.steps:
            run.steps.append(WorkflowStep(workflow_id=run.id, agent_name=planned.responsible_agent or "CEASER", status=planned.state.lower(), metadata_json={"step_id": planned.step_id, "capability": planned.capability, "input_refs": planned.input_refs, "output_name": planned.output_name, "depends_on": planned.depends_on, "confirmation_required": planned.confirmation_required, "availability": "PENDING"}))
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

    def transition(self, run: WorkflowRun, action: str) -> WorkflowRun:
        if action == "approved":
            run.status = "approved"
        elif action == "archived":
            run.status = "archived"
        else:
            raise ValueError("Unsupported workflow action")
        AuditService(self.db).record(user_id=run.user_id, action=f"workflow_{action}", resource_type="workflow", resource_id=run.id, commit=False)
        self.db.commit()
        self.db.refresh(run)
        return run

    def delete(self, run: WorkflowRun) -> None:
        AuditService(self.db).record(user_id=run.user_id, action="workflow_deleted", resource_type="workflow", resource_id=run.id, commit=False)
        self.db.delete(run)
        self.db.commit()
