from __future__ import annotations

from sqlalchemy.orm import Session

from app.services.workflows.schemas import WorkflowExecutionResult
from app.services.workflows.workflow_context import WorkflowContext
from app.services.workflows.workflow_executor import WorkflowExecutor
from app.services.workflows.workflow_manager import WorkflowManager
from app.services.workflows.workflow_router import WorkflowRouter
from app.services.workflows.goal_orchestrator import GoalWorkflowOrchestrator
from app.models.integration import Integration


class WorkflowOrchestrator:
    def __init__(self, db: Session):
        self.db = db
        self.router = WorkflowRouter()
        self.context = WorkflowContext(db)
        self.manager = WorkflowManager(db)
        self.executor = WorkflowExecutor(db)

    def run(self, *, user_id: str, message: str, conversation_id: str | None = None, file_ids: list[str] | None = None) -> WorkflowExecutionResult:
        integrations = [item.provider for item in self.db.query(Integration).filter(Integration.user_id == user_id, Integration.status == "connected").all()]
        goal_plan = GoalWorkflowOrchestrator().plan(user_id=user_id, request=message, context={"integrations": integrations, "file_ids": file_ids or [], "current_conversation": conversation_id})
        if len(goal_plan.steps) > 1 or goal_plan.steps[0].capability in {"research.execute", "document.create", "presentation.create", "email.create_draft", "calendar.create_event", "calendar.update_event"}:
            run = self.manager.create_goal_plan(goal_plan)
            executed = self.executor.execute_goal_plan(run=run, plan=goal_plan)
            return self._goal_response(run, goal_plan, executed)
        context_bundle = self.context.build(user_id=user_id, message=message, selected_agents=[], conversation_id=conversation_id, file_ids=file_ids)
        plan = self.router.route(message=message, enabled_agents=context_bundle["user_context"]["enabled_agents"])
        selected_agents = [{"name": name, "enabled": True, "modules": []} for name in plan.agents]
        context_bundle["context"]["selected_agents"] = selected_agents
        context_bundle["context"]["integrations"] = {
            agent["name"]: self.context.integrations.for_agent(user_id=user_id, agent_name=agent["name"])
            for agent in selected_agents
        }
        run = self.manager.create(user_id=user_id, workflow_type=plan.workflow_type, agents=plan.agents, metadata={"plan": plan.model_dump(), "conversation_id": conversation_id, "message": message, "file_ids": file_ids or []})
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

    def resume_goal(self, *, user_id: str, workflow_id: str, confirmed: bool) -> WorkflowExecutionResult:
        run = self.manager.get(workflow_id, user_id)
        if not run or run.workflow_type != "goal_workflow":
            raise ValueError("Goal workflow not found.")
        pending = (run.metadata_json or {}).get("pending_confirmation") or {}
        if not confirmed:
            run.status = "cancelled"
            self.db.commit()
            return self._goal_response(run, GoalWorkflowPlan.model_validate(run.metadata_json["goal_plan"]), {"contributions": [], "response": "Workflow cancelled.", "summary": "Workflow cancelled."})
        plan = GoalWorkflowPlan.model_validate(run.metadata_json["goal_plan"])
        executed = self.executor.execute_goal_plan(run=run, plan=plan, confirmed_capability=pending.get("capability"))
        return self._goal_response(run, plan, executed)

    @staticmethod
    def _goal_response(run, plan, executed) -> WorkflowExecutionResult:
        return WorkflowExecutionResult(workflow_id=run.id, workflow_type=run.workflow_type, status=run.status, selected_agents=list(dict.fromkeys(step.responsible_agent for step in plan.steps if step.responsible_agent)), contributions=executed.get("contributions", []), final_response=executed.get("response", ""), result_summary=executed.get("summary", ""), steps=[{"id": step.id, "agent_name": step.agent_name, "capability": step.metadata_json.get("capability"), "status": step.status, "output_summary": step.output_summary, "verified": step.metadata_json.get("verified", False)} for step in run.steps])
