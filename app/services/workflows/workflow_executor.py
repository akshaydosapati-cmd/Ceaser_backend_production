from __future__ import annotations

from sqlalchemy.orm import Session

from app.agents.registry import AgentRegistry
from app.models.mixins import utc_now
from app.models.workflow import WorkflowRun, WorkflowStep
from app.services.audit_service import AuditService
from app.services.workflows.workflow_merger import WorkflowMerger
from app.services.llm.workflow_llm_provider import WorkflowLLMProvider
from app.services.workflows.capability_executor import WorkflowCapabilityExecutor
from app.services.workflows.schemas import GoalWorkflowPlan


class WorkflowExecutor:
    def __init__(self, db: Session):
        self.db = db
        self.registry = AgentRegistry(provider=WorkflowLLMProvider())
        self.merger = WorkflowMerger()
        self.capabilities = WorkflowCapabilityExecutor(db)

    def execute_goal_plan(self, *, run: WorkflowRun, plan: GoalWorkflowPlan, confirmed_capability: str | None = None) -> dict:
        run.status, run.started_at = "running", run.started_at or utc_now()
        metadata = dict(run.metadata_json or {})
        outputs = dict(metadata.get("outputs") or {})
        plan_steps = {item.step_id: item for item in plan.steps}
        stored_steps = {str(item.metadata_json.get("step_id")): item for item in run.steps}
        while True:
            progressed = False
            for planned in plan.steps:
                step = stored_steps[planned.step_id]
                if step.status == "completed":
                    continue
                dependency_states = [stored_steps[item].status for item in planned.depends_on]
                if any(state in {"failed", "waiting_for_user", "waiting_for_device"} for state in dependency_states):
                    continue
                if not all(state == "completed" for state in dependency_states):
                    continue
                availability = self.capabilities.availability(planned.capability, run.user_id)
                step.metadata_json = {**step.metadata_json, "availability": availability}
                if availability == "REQUIRES_INTEGRATION":
                    step.status, run.status = "waiting_for_user", "waiting_for_user"
                    step.output_summary = f"Connect the required integration for {planned.capability}."
                    self._persist_goal_state(run, plan, outputs)
                    return self._goal_result(run, outputs)
                if availability == "UNAVAILABLE":
                    metadata = dict(run.metadata_json or {})
                    attempted = list(metadata.get("replan_attempts") or [])
                    if planned.capability not in attempted:
                        attempted.append(planned.capability)
                    metadata["replan_attempts"] = attempted[:1]
                    metadata["replan_exhausted"] = True
                    run.metadata_json = metadata
                    step.status = "failed"
                    step.output_summary = f"Capability unavailable: {planned.capability}"
                    run.status = "failed"
                    self._persist_goal_state(run, plan, outputs)
                    return self._goal_result(run, outputs)
                if planned.confirmation_required and confirmed_capability != planned.capability:
                    step.status, run.status = "waiting_for_user", "waiting_for_user"
                    step.output_summary = f"Confirmation required for {planned.capability}."
                    metadata["pending_confirmation"] = {"capability": planned.capability, "step_id": planned.step_id}
                    run.metadata_json = metadata
                    self._persist_goal_state(run, plan, outputs)
                    return self._goal_result(run, outputs)
                step.status, step.started_at = "running", utc_now()
                step_inputs = {name: outputs[name] for name in planned.input_refs if name in outputs}
                outcome = self.capabilities.execute(planned.capability, user_id=run.user_id, request=plan.goal.original_request, inputs=step_inputs, confirmed=confirmed_capability == planned.capability)
                step.status = outcome.state.lower()
                step.output_summary = outcome.message
                step.metadata_json = {**step.metadata_json, "verified": outcome.verified, "output": outcome.output}
                if outcome.state == "COMPLETED" and outcome.verified and outcome.output is not None:
                    outputs[planned.output_name] = outcome.output
                    step.completed_at = utc_now()
                    progressed = True
                    continue
                if outcome.state == "COMPLETED" and not outcome.verified:
                    step.status = "failed"
                    step.output_summary = outcome.message or f"{planned.capability} did not return a verified output."
                    run.status = "failed"
                else:
                    run.status = outcome.state.lower()
                self._persist_goal_state(run, plan, outputs)
                return self._goal_result(run, outputs)
            if all(item.status == "completed" for item in run.steps):
                run.status, run.completed_at = "completed", utc_now()
                run.result_summary = "All required workflow outputs were verified."
                metadata.pop("pending_confirmation", None)
                run.metadata_json = metadata
                self._persist_goal_state(run, plan, outputs)
                return self._goal_result(run, outputs)
            if not progressed:
                run.status = "failed"
                run.result_summary = "Workflow stopped because its remaining dependencies could not be resolved."
                self._persist_goal_state(run, plan, outputs)
                return self._goal_result(run, outputs)

    def _persist_goal_state(self, run: WorkflowRun, plan: GoalWorkflowPlan, outputs: dict) -> None:
        metadata = dict(run.metadata_json or {})
        metadata["outputs"] = outputs
        metadata["goal_plan"] = plan.model_dump(mode="json")
        run.metadata_json = metadata
        self.db.commit()
        self.db.refresh(run)

    @staticmethod
    def _goal_result(run: WorkflowRun, outputs: dict) -> dict:
        contributions = [{"capability": step.metadata_json.get("capability"), "status": step.status, "verified": step.metadata_json.get("verified", False), "output": step.metadata_json.get("output")} for step in run.steps]
        response = run.result_summary or next((step.output_summary for step in reversed(run.steps) if step.output_summary), "Workflow updated.")
        return {"run": run, "contributions": contributions, "response": response, "summary": response, "outputs": outputs}

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
