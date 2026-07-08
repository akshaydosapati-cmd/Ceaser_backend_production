from __future__ import annotations


class DraftSchemaRegistry:
    schemas: dict[str, dict] = {
        "pitch_deck": {
            "draft_type": "pitch_deck",
            "target_app": "powerpoint",
            "slides": [{"slide_number": 1, "title": "", "purpose": "", "bullets": [], "visual_suggestion": "", "speaker_notes": "", "memory_references": [], "source_references": []}],
        },
        "business_plan": {
            "draft_type": "business_plan",
            "target_app": "word",
            "sections": [{"heading": "", "summary": "", "details": [], "recommendations": []}],
        },
        "revenue_model": {"draft_type": "revenue_model", "target_app": "excel", "assumptions": [], "tables": [], "chart_suggestions": []},
        "swot_report": {"draft_type": "swot_report", "target_app": "word", "strengths": [], "weaknesses": [], "opportunities": [], "threats": [], "recommendations": []},
        "go_to_market_plan": {"draft_type": "go_to_market_plan", "target_app": "word", "segments": [], "channels": [], "positioning": [], "launch_steps": []},
        "research_report": {"draft_type": "research_report", "target_app": "word", "research_question": "", "executive_summary": "", "key_findings": [], "risks": [], "recommendations": [], "next_research_steps": [], "sources": []},
        "competitor_analysis": {"draft_type": "competitor_analysis", "target_app": "word", "competitors": [], "comparison": [], "opportunities": [], "recommendations": []},
        "market_overview": {"draft_type": "market_overview", "target_app": "word", "market_summary": "", "segments": [], "trends": [], "recommendations": []},
        "trend_report": {"draft_type": "trend_report", "target_app": "word", "trend_summary": "", "signals": [], "implications": [], "recommendations": []},
        "architecture_plan": {"draft_type": "architecture_plan", "target_app": "word", "system_goal": "", "architecture_summary": "", "modules": [], "apis": [], "database_design": [], "risks": [], "implementation_steps": []},
        "technical_spec": {"draft_type": "technical_spec", "target_app": "word", "overview": "", "requirements": [], "components": [], "apis": [], "risks": []},
        "api_documentation": {"draft_type": "api_documentation", "target_app": "word", "overview": "", "endpoints": [], "auth": [], "examples": []},
        "implementation_plan": {"draft_type": "implementation_plan", "target_app": "word", "objective": "", "phases": [], "tasks": [], "risks": []},
        "content_calendar": {"draft_type": "content_calendar", "target_app": "excel", "platforms": [], "calendar_items": []},
        "campaign_plan": {"draft_type": "campaign_plan", "target_app": "word", "objective": "", "audience": [], "messages": [], "channels": [], "timeline": []},
        "social_strategy": {"draft_type": "social_strategy", "target_app": "word", "platforms": [], "pillars": [], "posting_strategy": [], "metrics": []},
        "content_pack": {"draft_type": "content_pack", "target_app": "word", "assets": [], "captions": [], "visual_directions": []},
        "study_plan": {"draft_type": "study_plan", "target_app": "word", "goal": "", "timeline": "", "topics": [], "daily_plan": [], "revision_schedule": [], "resources": []},
        "learning_roadmap": {"draft_type": "learning_roadmap", "target_app": "word", "goal": "", "milestones": [], "resources": [], "practice": []},
        "goal_plan": {"draft_type": "goal_plan", "target_app": "word", "goal": "", "milestones": [], "habits": [], "checkpoints": []},
        "travel_plan": {"draft_type": "travel_plan", "target_app": "word", "destination": "", "itinerary": [], "budget": [], "checklist": []},
        "execution_plan": {"draft_type": "execution_plan", "target_app": "excel", "objective": "", "milestones": [], "risks": [], "follow_ups": []},
        "task_breakdown": {"draft_type": "task_breakdown", "target_app": "excel", "objective": "", "tasks": [], "owners": [], "dependencies": []},
        "project_tracker": {"draft_type": "project_tracker", "target_app": "excel", "project": "", "milestones": [], "tasks": [], "status_columns": []},
        "workflow_plan": {"draft_type": "workflow_plan", "target_app": "excel", "workflow": "", "steps": [], "automations": [], "risks": []},
    }

    agent_defaults = {
        "zeus": "business_plan",
        "nova": "research_report",
        "atlas": "architecture_plan",
        "friday": "content_calendar",
        "alex": "study_plan",
        "bolt": "execution_plan",
    }

    def get(self, draft_type: str) -> dict:
        return self.schemas[draft_type]

    def target_app(self, draft_type: str) -> str:
        return self.schemas.get(draft_type, {}).get("target_app", "keep_as_draft")
