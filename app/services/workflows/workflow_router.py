from __future__ import annotations

import re

from app.services.workflows.schemas import WorkflowPlan
from app.services.workflows.workflow_templates import WorkflowTemplateRegistry


class WorkflowRouter:
    def __init__(self):
        self.templates = WorkflowTemplateRegistry()

    def route(self, message: str, enabled_agents: list[dict]) -> WorkflowPlan:
        enabled = {agent["name"] for agent in enabled_agents}
        normalized = message.lower()
        workflow_type = self._detect(normalized)
        template = self.templates.get(workflow_type)
        agents = [agent for agent in template.agents if agent in enabled]
        if not agents and enabled:
            agents = [next(iter(enabled))]
        return WorkflowPlan(
            workflow_type=template.id,
            name=template.name,
            agents=agents,
            mode=template.mode,
            reason=f"Detected {template.name} from the user request.",
        )

    def _detect(self, message: str) -> str:
        creation_intent = re.search(r"\b(create|write|draft|generate|make|prepare)\b", message)
        explicit_research = re.search(r"\b(research|search|sources|competitors|look up|web|latest|news|find sources|cite|citations)\b", message)
        if creation_intent and re.search(r"\b(document|doc|article|essay|brief|writeup|write-up)\b", message) and not explicit_research:
            return "document"
        if creation_intent and re.search(r"\b(linkedin|youtube|campaign|post|content|calendar|marketing copy|social)\b", message) and not explicit_research:
            return "content"
        if re.search(r"\b(job application|resume|cover letter|interview|sde|software development engineer|apply for|career)\b", message):
            return "career"
        if re.search(r"\b(architecture|technical|system design|saas architecture|design architecture|engineering)\b", message):
            return "technical"
        if re.search(r"\b(launch|go to market|go-to-market|startup launch|help me launch)\b", message):
            return "startup"
        if re.search(r"\b(roadmap|execution plan|execute|milestones|deadline|project plan)\b", message):
            return "execution"
        if (
            re.search(r"\b(build|create|develop)\b", message)
            and re.search(r"\b(startup|saas|platform|app)\b", message)
            and not re.search(r"\b(strategy|business plan|go-to-market|go to market)\b", message)
        ):
            return "build_strategy"
        if re.search(r"\b(exam|study|learn|revision|study plan|timetable|time table|assignment)\b", message):
            return "learning"
        if re.search(r"\b(content|linkedin|youtube|campaign|post|calendar)\b", message):
            return "research_content"
        if re.search(r"\b(strategy|business plan|startup plan|revenue|growth|investor|market strategy)\b", message):
            return "research_strategy"
        if re.search(r"\b(research|search|sources|competitors|market|trend|look up|web)\b", message):
            return "research"
        return "research_strategy"
