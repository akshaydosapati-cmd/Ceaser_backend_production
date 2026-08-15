from __future__ import annotations

from collections.abc import Callable
from typing import Any
from uuid import uuid4

from app.agents.v2.context_builder import AgentContextBuilder
from app.agents.v2.models import AgentEvent, AgentResult, AgentTaskStatus, VerificationEvidence
from app.agents.v2.registry import AgentRegistry
from app.agents.v2.selector import AgentSelector


AgentRunner = Callable[[str, dict[str, Any]], AgentResult]


class AgentOrchestrator:
    def __init__(self, registry: AgentRegistry | None = None, selector: AgentSelector | None = None, *, max_agents: int = 3):
        self.registry = registry or AgentRegistry()
        self.selector = selector or AgentSelector()
        self.context_builder = AgentContextBuilder()
        self.max_agents = max(1, min(max_agents, 3))
        self.events: list[AgentEvent] = []

    def select(self, message: str, *, active_agent_id: str | None = None, channel: str = "text"):
        return self.selector.select(message, active_agent_id=active_agent_id, channel=channel)

    def prepare(self, message: str, context: dict[str, Any], *, channel: str = "text") -> dict[str, Any] | None:
        """Prepare bounded specialist context for the existing model path."""
        selection = self.select(message, active_agent_id=context.get("active_agent_id"), channel=channel)
        if selection.route != "SPECIALIST":
            return None
        task_id = context.get("task_id") or f"agent_{uuid4().hex}"
        agents: list[dict[str, Any]] = []
        seen: set[str] = set()
        for agent_id in selection.agent_ids[: self.max_agents]:
            if agent_id in seen:
                continue
            seen.add(agent_id)
            definition = self.registry.get(agent_id)
            if not definition:
                continue
            self._event("agent.selected", task_id, agent_id, AgentTaskStatus.CREATED)
            self._event("agent.planning", task_id, agent_id, AgentTaskStatus.PLANNING)
            agents.append({
                "definition": definition.model_dump(mode="json"),
                "context": self.context_builder.build(definition, message, context),
            })
        return {
            "task_id": task_id,
            "status": AgentTaskStatus.PLANNING.value,
            "selection": selection.model_dump(mode="json"),
            "agents": agents,
        }

    def run(self, message: str, context: dict[str, Any], runner: AgentRunner, *, channel: str = "text") -> list[AgentResult]:
        selection = self.select(message, active_agent_id=context.get("active_agent_id"), channel=channel)
        if selection.route != "SPECIALIST":
            return []
        task_id = context.get("task_id") or f"agent_{uuid4().hex}"
        results: list[AgentResult] = []
        seen: set[str] = set()
        for agent_id in selection.agent_ids[: self.max_agents]:
            if agent_id in seen:
                continue
            seen.add(agent_id)
            definition = self.registry.get(agent_id)
            if not definition:
                continue
            self._event("agent.selected", task_id, agent_id, AgentTaskStatus.CREATED)
            self._event("agent.started", task_id, agent_id, AgentTaskStatus.RUNNING)
            scoped = self.context_builder.build(definition, message, {**context, "previous_agent_results": [item.model_dump() for item in results]})
            result = runner(agent_id, scoped)
            if result.status == AgentTaskStatus.COMPLETED and not result.verification.verified:
                result = AgentResult(
                    task_id=result.task_id, agent_id=result.agent_id, status=AgentTaskStatus.FAILED,
                    summary="Agent output failed verification.", outputs=result.outputs, actions_taken=result.actions_taken,
                    execution_targets_used=result.execution_targets_used, capabilities_used=result.capabilities_used,
                    files_changed=result.files_changed, verification=VerificationEvidence(verified=False, summary="Verification evidence missing."),
                    blockers=[*result.blockers, "verification_required"], metadata=result.metadata,
                )
            self._event("agent.completed" if result.status == AgentTaskStatus.COMPLETED else "agent.failed", task_id, agent_id, result.status)
            results.append(result)
        return results

    def capability_allowed(self, agent_id: str, capability: str, *, user_authorized: bool, confirmed: bool, requires_confirmation: bool) -> bool:
        return user_authorized and self.registry.capability_allowed(agent_id, capability) and (confirmed or not requires_confirmation)

    def place_action(self, request, **availability):
        """Delegate execution location without making agents placement-aware."""
        from app.execution.placement import ExecutionPlacementEngine

        return ExecutionPlacementEngine().place(request, **availability)

    def _event(self, event: str, task_id: str, agent_id: str | None, status: AgentTaskStatus) -> None:
        self.events.append(AgentEvent(event=event, task_id=task_id, agent_id=agent_id, status=status))
