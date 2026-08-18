from __future__ import annotations

import re
from uuid import uuid4

from app.core.config.settings import settings
from app.services.capabilities.registry import CapabilityRegistry
from app.services.workflows.schemas import GoalWorkflowPlan, GoalWorkflowStep, UserGoal


class GoalWorkflowOrchestrator:
    """Capability-first planner layered over the existing WorkflowRunner."""

    def __init__(self, registry: CapabilityRegistry | None = None):
        self.registry = registry or CapabilityRegistry()

    def plan(self, *, user_id: str, request: str, context: dict | None = None) -> GoalWorkflowPlan:
        context = context or {}
        lowered = request.lower()
        requested: list[tuple[str, str | None, str]] = []
        if re.search(r"\b(research|latest|current|sources?|find out)\b", lowered):
            requested.append(("research.execute", "Alex", "research_result"))
        if re.search(r"\b(report|document|docx|pdf|revision sheet|notes)\b", lowered):
            requested.append(("document.create", "Atlas", "document_artifact"))
        if re.search(r"\b(presentation|slides?|deck|speaker notes)\b", lowered):
            requested.append(("presentation.create", "Nova", "presentation_artifact"))
        if re.search(r"\b(spreadsheet|workbook|excel|cost sheet)\b", lowered):
            requested.append(("spreadsheet.update", None, "spreadsheet_artifact"))
        if re.search(r"\b(email|mail|gmail|outlook)\b", lowered):
            requested.append(("email.create_draft", "Friday", "email_draft"))
        if re.search(r"\b(calendar|meeting|event|schedule|move it to)\b", lowered):
            requested.append(("calendar.update_event" if re.search(r"\b(move|reschedule|update)\b", lowered) else "calendar.create_event", "Friday", "calendar_event"))
        if re.search(r"\b(build|code|develop|implement|fix)\b", lowered):
            requested.append(("project.build", "Bolt", "build_result"))
        if not requested:
            matched = self.registry.match(request)
            requested.append((matched.id if matched else "ai.answer", matched.owner_agent if matched else None, "result"))

        steps: list[GoalWorkflowStep] = []
        missing: list[str] = []
        previous: str | None = None
        for index, (capability_id, agent, output) in enumerate(requested, 1):
            capability = self.registry.get(capability_id)
            integration_missing = self._integration_missing(capability_id, context.get("integrations", []))
            if not capability or integration_missing:
                missing.append(capability_id)
            step_id = f"step_{index}"
            protected = capability_id in {"email.send", "github.push", "browser.upload", "calendar.update_event"}
            steps.append(GoalWorkflowStep(step_id=step_id, capability=capability_id, responsible_agent=agent, execution_target=self._target(capability), input_refs=[steps[-1].output_name] if steps else [], output_name=output, depends_on=[previous] if previous else [], confirmation_required=protected, verification_rule=f"verified {output} exists", failure_strategy="wait_for_user" if protected else "replan"))
            previous = step_id
        goal = UserGoal(goal_id=uuid4().hex, user_id=user_id, original_request=request, inferred_outcome=self._outcome(request), active_project=context.get("active_project"), relevant_context=context.get("relevant_context", {}), known_files=context.get("file_ids", []), available_integrations=context.get("integrations", []), available_devices=context.get("devices", []), constraints=["desktop-first", "bounded-replanning", "verified-output-only"], required_confirmations=[s.capability for s in steps if s.confirmation_required], requested_deadline=context.get("requested_deadline"), current_conversation=context.get("current_conversation"), relevant_memory=context.get("relevant_memory", {}))
        estimate = sum(settings.credit_costs.get("research" if s.capability == "research.execute" else "agent_workflow", 0) for s in steps if self._target(self.registry.get(s.capability)) != "DEVICE")
        return GoalWorkflowPlan(workflow_id=uuid4().hex, goal=goal, steps=steps, state="WAITING_FOR_USER" if missing else "PLANNED", estimated_credits=estimate, missing_capabilities=missing)

    @staticmethod
    def _outcome(request: str) -> str:
        return " ".join(request.strip().split())[:500]

    @staticmethod
    def _target(capability) -> str:
        if not capability:
            return "UNAVAILABLE"
        targets = [getattr(item, "value", str(item)) for item in capability.allowed_execution_targets]
        for preferred in ("CLOUD", "DEVICE", "NONE"):
            if preferred in targets:
                return preferred
        return targets[0] if targets else "NONE"

    @staticmethod
    def _integration_missing(capability_id: str, integrations: list[str]) -> bool:
        providers = {item.lower() for item in integrations}
        if capability_id.startswith("email."):
            return not providers.intersection({"gmail", "outlook"})
        if capability_id.startswith("calendar."):
            return not providers.intersection({"google-calendar", "outlook-calendar"})
        return False
