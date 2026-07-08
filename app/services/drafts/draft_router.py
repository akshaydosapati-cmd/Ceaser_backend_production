from __future__ import annotations


class DraftRouter:
    def route(self, prompt: str, draft_type: str | None = None, agent_id: str | None = None) -> tuple[str, str]:
        if agent_id:
            return agent_id, draft_type or self._type_from_prompt_for_agent(prompt, agent_id)
        text = f"{prompt} {draft_type or ''}".lower()
        if "competitor" in text:
            return "nova", "competitor_analysis"
        if "research" in text:
            return "nova", "research_report"
        if "trend" in text:
            return "nova", "trend_report"
        if "market overview" in text or "industry" in text:
            return "nova", "market_overview"
        if any(term in text for term in ["architecture", "system design"]):
            return "atlas", "architecture_plan"
        if "api" in text:
            return "atlas", "api_documentation"
        if "technical" in text:
            return "atlas", "technical_spec"
        if "implementation" in text:
            return "atlas", "implementation_plan"
        if "calendar" in text:
            return "friday", "content_calendar"
        if "campaign" in text:
            return "friday", "campaign_plan"
        if "social" in text:
            return "friday", "social_strategy"
        if "content" in text:
            return "friday", "content_pack"
        if "learning" in text:
            return "alex", "learning_roadmap"
        if "goal" in text:
            return "alex", "goal_plan"
        if "travel" in text:
            return "alex", "travel_plan"
        if "study" in text or "exam" in text:
            return "alex", "study_plan"
        if "task" in text:
            return "bolt", "task_breakdown"
        if "workflow" in text:
            return "bolt", "workflow_plan"
        if "tracker" in text:
            return "bolt", "project_tracker"
        if "execution" in text or "launch" in text:
            return "bolt", "execution_plan"
        if any(term in text for term in ["pitch", "presentation", "deck"]):
            return "zeus", "pitch_deck"
        if "revenue" in text:
            return "zeus", "revenue_model"
        if "swot" in text:
            return "zeus", "swot_report"
        if "go to market" in text or "gtm" in text:
            return "zeus", "go_to_market_plan"
        return "zeus", draft_type or "business_plan"

    @staticmethod
    def _type_from_agent(agent_id: str) -> str:
        return {
            "zeus": "business_plan",
            "nova": "research_report",
            "atlas": "architecture_plan",
            "friday": "content_calendar",
            "alex": "study_plan",
            "bolt": "execution_plan",
        }.get(agent_id, "business_plan")

    def _type_from_prompt_for_agent(self, prompt: str, agent_id: str) -> str:
        routed_agent, routed_type = self.route(prompt)
        return routed_type if routed_agent == agent_id else self._type_from_agent(agent_id)
