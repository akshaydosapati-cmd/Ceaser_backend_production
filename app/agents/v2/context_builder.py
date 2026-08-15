from __future__ import annotations

from typing import Any

from app.agents.v2.models import AgentDefinition


class AgentContextBuilder:
    def build(self, definition: AgentDefinition, request: str, context: dict[str, Any]) -> dict[str, Any]:
        allowed = set(definition.memory_context_scope)
        result: dict[str, Any] = {"request": request, "agent_id": definition.id}
        if "conversation" in allowed:
            result["conversation"] = list(context.get("conversation", []))[-8:]
            result["active_topic"] = context.get("active_topic")
        if "active_project" in allowed and context.get("active_project"):
            result["active_project"] = context["active_project"]
        if "relevant_memory" in allowed:
            result["memories"] = list(context.get("relevant_memories", []))[:5]
        if context.get("previous_agent_results"):
            result["previous_agent_results"] = list(context["previous_agent_results"])[-3:]
        result["execution_environment"] = context.get("execution_environment", {})
        result["available_capabilities"] = [
            capability for capability in context.get("available_capabilities", []) if definition.permits(capability)
        ]
        return result
