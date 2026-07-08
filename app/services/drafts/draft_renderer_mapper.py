from __future__ import annotations


class DraftRendererMapper:
    renderers = {
        "pitch_deck": "slide_cards",
        "business_plan": "section_cards",
        "revenue_model": "table_model",
        "swot_report": "swot_grid",
        "go_to_market_plan": "plan_cards",
        "research_report": "findings_layout",
        "competitor_analysis": "comparison_layout",
        "market_overview": "market_cards",
        "trend_report": "trend_cards",
        "architecture_plan": "module_cards",
        "technical_spec": "module_cards",
        "api_documentation": "api_cards",
        "implementation_plan": "timeline_cards",
        "content_calendar": "calendar_table",
        "campaign_plan": "plan_cards",
        "social_strategy": "plan_cards",
        "content_pack": "content_cards",
        "study_plan": "study_timeline",
        "learning_roadmap": "timeline_cards",
        "goal_plan": "timeline_cards",
        "travel_plan": "timeline_cards",
        "execution_plan": "milestone_board",
        "task_breakdown": "task_board",
        "project_tracker": "task_board",
        "workflow_plan": "workflow_steps",
    }

    def renderer_for(self, draft_type: str) -> str:
        return self.renderers.get(draft_type, "section_cards")
