from __future__ import annotations

from app.intelligence.actions.engine import ActionEngine
from app.intelligence.workflows.models import WorkflowPlan


class WorkflowEngine:
    def __init__(self, action_engine: ActionEngine | None = None) -> None:
        self.action_engine = action_engine or ActionEngine()

    async def preview(self, plan: WorkflowPlan) -> dict:
        return {
            "workflow_type": plan.workflow_type,
            "output_format": plan.output_format,
            "steps": [
                {
                    "name": step.name,
                    "kind": step.kind,
                    "requires_confirmation": step.requires_confirmation,
                }
                for step in plan.steps
            ],
        }

