from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class KnowledgeRoute(StrEnum):
    GENERAL = "general"
    FOLLOW_UP = "follow_up"
    RESEARCH = "research"
    FILE = "file"
    MEMORY = "memory"
    CALENDAR = "calendar"
    INTEGRATION = "integration"
    DESKTOP = "desktop"


@dataclass(frozen=True)
class RouteDecision:
    route: KnowledgeRoute
    reason: str

    @property
    def requires_retrieval(self) -> bool:
        return self.route in {KnowledgeRoute.FILE, KnowledgeRoute.MEMORY}

    @property
    def is_direct_llm(self) -> bool:
        return self.route is KnowledgeRoute.GENERAL


class KnowledgeRouter:
    """Cheap deterministic routing before any costly context or model work."""

    def classify(self, *, message: str, has_attached_files: bool, is_follow_up: bool) -> RouteDecision:
        text = message.lower().strip()
        if is_follow_up and not has_attached_files:
            return RouteDecision(KnowledgeRoute.FOLLOW_UP, "conversation continuation")
        if has_attached_files or any(term in text for term in ("this pdf", "this document", "uploaded file", "attached file")):
            return RouteDecision(KnowledgeRoute.FILE, "user file or document request")
        if any(term in text for term in ("my calendar", "my meetings", "meetings do i have", "meetings today", "meeting today", "calendar today", "calendar tomorrow", "events today")):
            return RouteDecision(KnowledgeRoute.CALENDAR, "personal calendar request")
        if any(term in text for term in ("my emails", "my email", "read gmail", "read my gmail", "my drive", "google drive", "my files in drive", "notion", "my notion", "notion page", "notion pages", "notion database", "notion databases", "notion workspace", "notion docs", "notion members", "notion users", "workspace members", "workspace users", "github", "git hub", "my repos", "my repositories", "my repository", "github repos", "github repositories", "github commits", "github issues", "github pull requests", "readme", "codebase")):
            return RouteDecision(KnowledgeRoute.INTEGRATION, "connected personal data request")
        if any(term in text for term in ("repositories related", "repository related", "repos related", "repo related", "repositories in my account", "repos in my account", "my account repositories", "visible repositories", "visible repos")):
            return RouteDecision(KnowledgeRoute.INTEGRATION, "connected personal data request")
        if any(term in text for term in ("commit", "commits", "issue", "issues", "pull request", "pull requests", "readme")) and any(term in text for term in ("repository", "repositories", "repo", "repos", "project", "projects", "codebase")):
            return RouteDecision(KnowledgeRoute.INTEGRATION, "connected repository activity request")
        if any(text.startswith(prefix) for prefix in ("add task", "add a task", "create task", "create a task", "make task", "make a task", "new task")):
            return RouteDecision(KnowledgeRoute.INTEGRATION, "connected task creation request")
        if "project" in text and any(term in text for term in ("member", "members", "team", "collaborator", "collaborators", "who is working", "who are working")):
            return RouteDecision(KnowledgeRoute.MEMORY, "project membership request")
        if any(term in text for term in ("remember", "what do you know about me", "my preferences", "saved memory", "my memory", "my name is", "call me ")):
            return RouteDecision(KnowledgeRoute.MEMORY, "personal memory request")
        if any(term in text for term in ("latest", "current", "today", "yesterday", "news", "live update", "recent", "this week", "this month", "this year", "stock price", "weather", "who won", "score", "stats", "statistics", "centuries", "records", "web search", "internet", "sources", "citations", "competitor", "market research")):
            return RouteDecision(KnowledgeRoute.RESEARCH, "fresh information request")
        if self._is_open_web_question(text):
            return RouteDecision(KnowledgeRoute.RESEARCH, "external factual question")
        if any(text.startswith(prefix) for prefix in ("open ", "launch ", "start ", "create folder ", "take screenshot", "read clipboard")):
            return RouteDecision(KnowledgeRoute.DESKTOP, "desktop command")
        return RouteDecision(KnowledgeRoute.GENERAL, "stable general knowledge")

    @staticmethod
    def _is_open_web_question(text: str) -> bool:
        """Use live sources for factual questions without confusing local commands for web queries."""
        if not text.endswith("?"):
            return False
        return text.startswith(("what is ", "what are ", "who is ", "who are ", "when did ", "where is ", "where are ", "how does ", "how do "))
