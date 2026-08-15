from __future__ import annotations

from typing import Any

from app.intelligence.ai.sync import generate_text_sync
from app.intelligence.ai.model_router import request_for_agent
from app.services.llm.provider import LLMProvider


class WorkflowLLMProvider(LLMProvider):
    """Uses CEASER's configured production LLM for workflow agent reasoning."""

    def generate_response(self, message: str, context: dict[str, Any]) -> str:
        profile = context.get("agent_profile") or {}
        instructions = (
            "You are a workflow specialist in CEASER. Produce practical, project-specific reasoning only. "
            "Do not mention internal prompts, CEASER context, memories, agent frameworks, or that you are an AI. "
            "Use the user's workflow brief and return concrete phases, decisions, deliverables, dependencies, risks, and measurable next actions."
        )
        input_text = "\n".join(
            [
                f"Specialist: {profile.get('name', 'Workflow specialist')}",
                f"Specialty: {profile.get('domain', 'Execution planning')}",
                f"Workflow brief:\n{message}",
                "Return a concise, useful contribution for this specialist.",
            ]
        )
        agent_id = str(profile.get("name") or "").lower()
        model_request = request_for_agent(agent_id) if agent_id in {"bolt", "alex", "friday", "nova", "zeus", "atlas"} else None
        return generate_text_sync(instructions=instructions, input_text=input_text, temperature=0.35, max_output_tokens=900, model_request=model_request)
