from __future__ import annotations

from sqlalchemy.orm import Session

from app.services.workflows.schemas import WorkflowExecutionResult
from app.services.workflows.workflow_context import WorkflowContext
from app.services.workflows.workflow_executor import WorkflowExecutor
from app.services.workflows.workflow_manager import WorkflowManager
from app.services.workflows.workflow_router import WorkflowRouter


class WorkflowOrchestrator:
    def __init__(self, db: Session):
        self.db = db
        self.router = WorkflowRouter()
        self.context = WorkflowContext(db)
        self.manager = WorkflowManager(db)
        self.executor = WorkflowExecutor(db)

    def run(self, *, user_id: str, message: str, conversation_id: str | None = None, file_ids: list[str] | None = None) -> WorkflowExecutionResult:
        context_bundle = self.context.build(user_id=user_id, message=message, selected_agents=[], conversation_id=conversation_id, file_ids=file_ids)
        plan = self.router.route(message=message, enabled_agents=context_bundle["user_context"]["enabled_agents"])
        selected_agents = [{"name": name, "enabled": True, "modules": []} for name in plan.agents]
        context_bundle["context"]["selected_agents"] = selected_agents
        context_bundle["context"]["integrations"] = {
            agent["name"]: self.context.integrations.for_agent(user_id=user_id, agent_name=agent["name"])
            for agent in selected_agents
        }
        run = self.manager.create(user_id=user_id, workflow_type=plan.workflow_type, agents=plan.agents, metadata={"plan": plan.model_dump(), "conversation_id": conversation_id})
        executed = self.executor.execute(run=run, workflow_name=plan.name, base_context=context_bundle["context"])
        steps = [
            {
                "id": step.id,
                "agent_name": step.agent_name,
                "status": step.status,
                "output_summary": step.output_summary,
                "started_at": step.started_at.isoformat() if step.started_at else None,
                "completed_at": step.completed_at.isoformat() if step.completed_at else None,
            }
            for step in run.steps
        ]
        return WorkflowExecutionResult(
            workflow_id=run.id,
            workflow_type=run.workflow_type,
            status=run.status,
            selected_agents=plan.agents,
            contributions=executed["contributions"],
            final_response=executed["response"],
            result_summary=executed["summary"],
            steps=steps,
        )
