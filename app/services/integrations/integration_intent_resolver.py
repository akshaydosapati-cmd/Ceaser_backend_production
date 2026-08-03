from __future__ import annotations

from dataclasses import dataclass, field
import re


@dataclass(frozen=True)
class IntegrationIntent:
    provider: str
    capability: str
    entities: dict[str, str] = field(default_factory=dict)
    confidence: float = 0.8
    needs_clarification: bool = False


class IntegrationIntentResolver:
    """Resolve user integration requests into provider capabilities."""

    def resolve(self, message: str) -> IntegrationIntent | None:
        normalized = message.lower().strip()
        if self._is_github_request(normalized):
            return self._github_intent(message, normalized)
        if self._is_notion_request(normalized):
            return self._notion_intent(message, normalized)
        return None

    def _is_github_request(self, text: str) -> bool:
        return bool(
            re.search(r"\b(?:github|git hub|repository|repositories|repo|repos|readme|codebase)\b", text)
            or (
                re.search(r"\b(?:commit|commits|issue|issues|pull request|pull requests|pr|prs)\b", text)
                and re.search(r"\b(?:project|projects|repository|repositories|repo|repos|codebase)\b", text)
            )
        )

    def _github_intent(self, message: str, normalized: str) -> IntegrationIntent:
        repository_query = self._github_repository_query(message)
        entities = {"repository_query": repository_query} if repository_query else {}
        if re.search(r"\b(?:commit|commits|change|changes|recent changes)\b", normalized):
            return IntegrationIntent("github", "github.list_commits", entities, 0.94)
        if re.search(r"\b(?:issue|issues)\b", normalized):
            return IntegrationIntent("github", "github.list_issues", entities, 0.94)
        if re.search(r"\b(?:pull request|pull requests|pr|prs)\b", normalized):
            return IntegrationIntent("github", "github.list_pull_requests", entities, 0.94)
        if re.search(r"\b(?:readme|explain|describe)\b", normalized) and repository_query:
            return IntegrationIntent("github", "github.get_readme", entities, 0.9)
        if re.search(r"\b(?:summarize|summary|overview|working on|projects)\b", normalized):
            return IntegrationIntent("github", "github.summarize_repositories", entities, 0.88)
        if re.search(r"\b(?:find|search|related|called|named)\b", normalized) and repository_query:
            return IntegrationIntent("github", "github.resolve_repository", entities, 0.9)
        return IntegrationIntent("github", "github.list_repositories", entities, 0.82)

    def _github_repository_query(self, message: str) -> str:
        cleaned = re.sub(
            r"\b(?:github|git hub|my|repository|repositories|repo|repos|commit|commits|issue|issues|pull|request|requests|prs|readme|codebase|read|find|search|show|list|summarize|summary|explain|use|check|sync|what|are|is|connected|to|from|in|account|visible|related|about|called|named|project|projects|of|for|the)\b",
            " ",
            message,
            flags=re.I,
        )
        cleaned = re.sub(r"\s+", " ", cleaned).strip(" .?!:\"'")
        return cleaned if len(cleaned) >= 3 else ""

    def _is_notion_request(self, text: str) -> bool:
        return bool(re.search(r"\b(?:notion|workspace|database|databases|page|pages|notes|tasks|assigned|assignee)\b", text))

    def _notion_intent(self, message: str, normalized: str) -> IntegrationIntent:
        query = self._notion_query(message)
        entities = {"query": query} if query else {}
        if re.search(r"\b(?:task|tasks|todo|to-do|assigned|assignee|assignment|owner|owners)\b", normalized):
            return IntegrationIntent("notion", "notion.list_tasks", entities, 0.93)
        if re.search(r"\b(?:database|databases)\b", normalized):
            return IntegrationIntent("notion", "notion.list_databases", entities, 0.9)
        if re.search(r"\b(?:summarize|summary|overview|workspace structure|workspace context|what you can see)\b", normalized):
            return IntegrationIntent("notion", "notion.summarize_workspace", entities, 0.9)
        if re.search(r"\b(?:find|search)\b", normalized) and query:
            return IntegrationIntent("notion", "notion.search_pages", entities, 0.88)
        return IntegrationIntent("notion", "notion.list_pages", entities, 0.82)

    def _notion_query(self, message: str) -> str:
        cleaned = re.sub(
            r"\b(?:notion|my|workspace|context|page|pages|database|databases|docs|documents|notes|read|find|search|show|list|summarize|summary|explain|use|check|sync|what|are|is|connected|to|from|in|account|ceaser|task|tasks|assigned|assignee|member|members)\b",
            " ",
            message,
            flags=re.I,
        )
        cleaned = re.sub(r"\s+", " ", cleaned).strip(" .?!:\"'")
        return cleaned if len(cleaned) >= 3 else ""
