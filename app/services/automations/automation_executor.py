from __future__ import annotations

from datetime import timedelta, timezone

from sqlalchemy.orm import Session

from app.core.config.settings import settings
from app.models.automation import Automation, AutomationRun
from app.models.mixins import utc_now
from app.services.audit_service import AuditService
from app.services.automations.automation_time import next_run_at
from app.services.integrations.integration_context_service import IntegrationContextService
from app.services.news import NewsService
from app.services.orchestrator import CeaserOrchestrator


AGENT_NAMES = {
    "nova": "Nova",
    "zeus": "Zeus",
    "friday": "Friday",
    "alex": "Alex",
    "bolt": "Bolt",
    "atlas": "Atlas",
}


class AutomationExecutor:
    def __init__(self, db: Session):
        self.db = db

    def run(self, automation: Automation) -> AutomationRun:
        run = AutomationRun(
            automation_id=automation.id,
            user_id=automation.user_id,
            workspace_id=automation.workspace_id,
            assigned_agent=automation.assigned_agent,
            status="running",
            metadata_json={"automation_type": automation.automation_type},
        )
        self.db.add(run)
        AuditService(self.db).record(user_id=automation.user_id, action="automation_run_started", resource_type="automation", resource_id=automation.id, commit=False)
        self.db.flush()

        try:
            prompt = self._build_prompt(automation)
            news_brief = self._news_brief(automation)
            if news_brief:
                prompt = f"{prompt}\n\nLive news context:\n{self._format_news_context(news_brief)}"
            response = CeaserOrchestrator(self.db).handle_message(user_id=automation.user_id, message=prompt)
            content = response.get("response", "")
            run.status = "completed"
            run.completed_at = utc_now()
            run.output_title = automation.name
            run.output_summary = self._summary(content)
            run.output_content = content
            run.metadata_json = {
                "selected_agents": response.get("selected_agents", []),
                "memory_count": len(response.get("memories_used", [])),
                "research": response.get("research"),
                "news": news_brief.model_dump() if news_brief else None,
                "integrations": IntegrationContextService(self.db).for_automation(automation.user_id, automation.automation_type),
                "context_summary": response.get("context_summary", {}),
            }
            automation.last_run_at = run.completed_at
            automation.config_json = {**(automation.config_json or {}), "failure_count": 0}
            automation.next_run_at = None if automation.trigger_frequency == "once" else next_run_at(
                frequency=automation.trigger_frequency,
                trigger_time=automation.trigger_time,
                tz_name=automation.timezone,
                from_time=run.completed_at.astimezone(timezone.utc),
            )
            AuditService(self.db).record(user_id=automation.user_id, action="automation_run_completed", resource_type="automation", resource_id=automation.id, metadata={"run_id": run.id}, commit=False)
        except Exception as exc:
            run.status = "failed"
            run.completed_at = utc_now()
            run.error_message = "Automation failed while generating the agent output."
            failure_count = int((automation.config_json or {}).get("failure_count", 0)) + 1
            retry_allowed = failure_count < settings.automation_worker_max_retries
            automation.config_json = {**(automation.config_json or {}), "failure_count": failure_count, "last_error": str(exc)}
            if retry_allowed:
                automation.next_run_at = utc_now() + timedelta(seconds=settings.automation_worker_retry_delay_seconds * failure_count)
            else:
                automation.config_json = {**automation.config_json, "failure_count": 0}
                automation.next_run_at = None if automation.trigger_frequency == "once" else next_run_at(
                    frequency=automation.trigger_frequency,
                    trigger_time=automation.trigger_time,
                    tz_name=automation.timezone,
                    from_time=run.completed_at.astimezone(timezone.utc),
                )
            run.metadata_json = {"automation_type": automation.automation_type, "failure_count": failure_count, "retry_scheduled": retry_allowed}
            AuditService(self.db).record(user_id=automation.user_id, action="automation_run_failed", resource_type="automation", resource_id=automation.id, metadata={"run_id": run.id, "error": str(exc), "retry_scheduled": retry_allowed}, commit=False)

        self.db.commit()
        self.db.refresh(run)
        return run

    def _build_prompt(self, automation: Automation) -> str:
        agent_name = AGENT_NAMES.get(automation.assigned_agent, automation.assigned_agent.title())
        base_prompt = automation.config_json.get("prompt") or automation.description or automation.name
        output_contract = self._output_contract(automation.automation_type)
        return (
            f"Run this CEASER agent automation as {agent_name}.\n\n"
            f"Automation: {automation.name}\n"
            f"Type: {automation.automation_type}\n"
            f"Instructions: {base_prompt}\n\n"
            "Return only the useful output for this automation. Do not write a long report unless the automation explicitly asks for one. "
            "Do not include internal agent routing, framework names, confidence scores, debug details, or filler explanation. "
            "Use CEASER memory, files, projects, integrations, and research only when directly relevant. "
            "Do not perform external desktop actions.\n\n"
            f"{output_contract}"
        )

    def _output_contract(self, automation_type: str) -> str:
        contracts = {
            "learning": (
                "Output format for learning automations:\n"
                "Study Plan\n"
                "Focus: one sentence.\n"
                "Time Blocks: 3-5 short blocks with time, topic, and task.\n"
                "Practice: 3 concrete practice tasks only.\n"
                "Revision: 3 quick revision points only.\n"
                "Keep the whole answer under 220 words."
            ),
            "news": (
                "Output format for news automations:\n"
                "News Brief\n"
                "Top Stories: 5 headlines max, each with one short explanation and source name.\n"
                "Why It Matters: 3 bullets max.\n"
                "Follow-ups: 2 bullets max.\n"
                "Use live news context when provided. Keep the whole answer under 260 words."
            ),
            "research": (
                "Output format for research automations:\n"
                "Research Brief\n"
                "Key Findings: 5 bullets max.\n"
                "Sources: 5 source names/links max when available.\n"
                "Implications: 3 bullets max.\n"
                "Next Questions: 2 bullets max.\n"
                "Keep the whole answer under 300 words."
            ),
            "business": (
                "Output format for business automations:\n"
                "Strategy Brief\n"
                "Decision Needed: one sentence.\n"
                "Signals: 3 bullets max.\n"
                "Recommended Moves: 3 bullets max.\n"
                "Risks: 2 bullets max.\n"
                "Keep the whole answer under 240 words."
            ),
            "content": (
                "Output format for content automations:\n"
                "Content Plan\n"
                "Goal: one sentence.\n"
                "Ideas: 5 ideas max with channel and angle.\n"
                "Best Draft: one short sample only.\n"
                "Schedule: 3 slots max.\n"
                "Keep the whole answer under 260 words."
            ),
            "execution": (
                "Output format for execution automations:\n"
                "Execution Plan\n"
                "Priority: one sentence.\n"
                "Tasks: 5 tasks max, each with owner/context and urgency.\n"
                "Blockers: 3 bullets max.\n"
                "Today: 3 actions max.\n"
                "Keep the whole answer under 220 words."
            ),
            "engineering": (
                "Output format for engineering automations:\n"
                "Technical Brief\n"
                "Objective: one sentence.\n"
                "Build Steps: 5 steps max.\n"
                "Risks: 3 bullets max.\n"
                "Validation: 3 checks max.\n"
                "Keep the whole answer under 260 words."
            ),
        }
        return contracts.get(
            automation_type,
            "Output format: concise title, 5 useful bullets max, and 3 next actions max. Keep the whole answer under 220 words.",
        )

    def _news_brief(self, automation: Automation):
        if automation.automation_type != "news":
            return None
        base_prompt = automation.config_json.get("prompt") or automation.description or automation.name
        return NewsService().for_automation(name=automation.name, prompt=base_prompt)

    def _format_news_context(self, news_brief) -> str:
        if news_brief.error and not news_brief.articles:
            return f"News provider error: {news_brief.error}"
        lines = [f"Provider: {news_brief.provider}", f"Mode: {news_brief.mode}", f"Query: {news_brief.query}", "Articles:"]
        for index, article in enumerate(news_brief.articles, start=1):
            parts = [
                f"{index}. {article.title}",
                f"Source: {article.source or 'Unknown'}",
                f"Published: {article.published_at or 'Unknown'}",
            ]
            if article.summary:
                parts.append(f"Summary: {article.summary}")
            if article.url:
                parts.append(f"URL: {article.url}")
            lines.append(" | ".join(parts))
        return "\n".join(lines)

    def _summary(self, content: str) -> str:
        cleaned = " ".join(content.replace("#", "").split())
        return cleaned[:420] + ("..." if len(cleaned) > 420 else "")
