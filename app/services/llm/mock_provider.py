from __future__ import annotations

from typing import Any

from app.services.llm.provider import LLMProvider


class MockProvider(LLMProvider):
    def generate_response(self, message: str, context: dict[str, Any]) -> str:
        if context.get("mode") == "agent_analysis":
            profile = context.get("agent_profile", {})
            agent = profile.get("name", "Agent")
            domain = profile.get("domain", "Specialist Intelligence")
            frameworks = ", ".join(profile.get("frameworks", [])[:2])
            memory_count = len(context.get("memories", []))
            return (
                f"{agent} analyzed the request through {domain}. "
                f"Framework focus: {frameworks or 'specialist reasoning'}. "
                f"Context used: {memory_count} ranked memories plus CEASER and project context."
            )

        merged = context.get("merged_contributions")
        if merged:
            return merged["response"]

        scope = context.get("scope", {}).get("type", "personal_ai_os")
        agents = ", ".join(agent["name"] for agent in context.get("selected_agents", [])) or "Bolt"
        memory_count = len(context.get("memories", []))
        project_count = len(context.get("projects", []))
        return (
            f"I understood: {message}\n\n"
            f"I am handling this inside CEASER's {scope} context with {agents}. "
            f"I found {memory_count} relevant memories and {project_count} active project records. "
            "For Sprint 3, this is the orchestrated planning response path; no agent execution or external LLM call has run yet."
        )
