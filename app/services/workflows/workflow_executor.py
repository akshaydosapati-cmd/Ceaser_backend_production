from __future__ import annotations

from sqlalchemy.orm import Session

from app.agents.registry import AgentRegistry
from app.models.mixins import utc_now
from app.models.workflow import WorkflowRun, WorkflowStep
from app.services.audit_service import AuditService
from app.services.workflows.workflow_merger import WorkflowMerger


class WorkflowExecutor:
    def __init__(self, db: Session):
        self.db = db
        self.registry = AgentRegistry()
        self.merger = WorkflowMerger()

    def execute(self, *, run: WorkflowRun, workflow_name: str, base_context: dict) -> dict:
        run.status = "running"
        run.started_at = utc_now()
        AuditService(self.db).record(user_id=run.user_id, action="workflow_started", resource_type="workflow", resource_id=run.id, commit=False)
        self.db.flush()

        contributions = []
        try:
            for step in run.steps:
                step.status = "running"
                step.started_at = utc_now()
                AuditService(self.db).record(user_id=run.user_id, action="workflow_step_started", resource_type="workflow_step", resource_id=step.id, metadata={"agent": step.agent_name}, commit=False)
                agent = self.registry.get(step.agent_name)
                if not agent:
                    raise RuntimeError(f"Agent not available: {step.agent_name}")
                step_context = {**base_context, "workflow_handoffs": contributions}
                contribution = agent.contribute(step_context)
                contributions.append(contribution)
                step.status = "completed"
                step.completed_at = utc_now()
                step.output_summary = self._summary(contribution.get("analysis", ""))
                step.metadata_json = {"contribution": contribution, "handoff_count": len(contributions) - 1}
                AuditService(self.db).record(user_id=run.user_id, action="workflow_step_completed", resource_type="workflow_step", resource_id=step.id, metadata={"agent": step.agent_name}, commit=False)

            merged = self.merger.merge(workflow_name=workflow_name, message=base_context.get("message", ""), contributions=contributions)
            run.status = "completed"
            run.completed_at = utc_now()
            run.result_summary = merged["summary"]
            run.metadata_json = {
                **(run.metadata_json or {}),
                "contributions": contributions,
                "next_actions": merged["next_actions"],
                "generated_response": merged["response"],
            }
            AuditService(self.db).record(user_id=run.user_id, action="workflow_completed", resource_type="workflow", resource_id=run.id, metadata={"agent_count": len(contributions)}, commit=False)
            self.db.commit()
            self.db.refresh(run)
            return {"run": run, "contributions": contributions, "response": merged["response"], "summary": merged["summary"]}
        except Exception as exc:
            run.status = "failed"
            run.completed_at = utc_now()
            run.result_summary = "Workflow failed before completion."
            run.metadata_json = {**(run.metadata_json or {}), "error": str(exc)}
            AuditService(self.db).record(user_id=run.user_id, action="workflow_failed", resource_type="workflow", resource_id=run.id, metadata={"error": str(exc)}, commit=False)
            self.db.commit()
            self.db.refresh(run)
            raise

    def _summary(self, value: str) -> str:
        cleaned = " ".join(value.split())
        return cleaned[:420] + ("..." if len(cleaned) > 420 else "")
