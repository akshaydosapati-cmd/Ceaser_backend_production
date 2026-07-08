from __future__ import annotations

import re

from app.config.agent_routing import AGENT_ROUTING_RULES, DEFAULT_AGENT


class AgentSelector:
    def select_agents(self, message: str, enabled_agents: list[dict]) -> list[dict]:
        enabled_by_name = {agent["name"]: agent for agent in enabled_agents}
        normalized = message.lower()
        tokens = set(re.findall(r"[a-z0-9]+", normalized))
        intent_selected = self._select_by_intent(normalized, tokens, enabled_by_name)
        if intent_selected:
            return intent_selected
        if self._is_memory_recall(normalized):
            return self._select_recall_agent(tokens=tokens, enabled_by_name=enabled_by_name)

        scored: list[tuple[int, str]] = []

        for agent_name, rule in AGENT_ROUTING_RULES.items():
            if agent_name not in enabled_by_name:
                continue
            if agent_name == "Atlas" and not self._has_build_intent(normalized, tokens):
                continue
            if agent_name == "Alex" and self._is_healthcare_domain(normalized):
                continue
            domains = set(rule.get("domains", []))
            matches = len(tokens & domains)
            if matches:
                scored.append((matches * int(rule.get("weight", 1)), agent_name))

        scored.sort(key=lambda item: (-item[0], item[1]))
        selected = [enabled_by_name[name] for _, name in scored[:3]]
        if not selected and DEFAULT_AGENT in enabled_by_name:
            selected = [enabled_by_name[DEFAULT_AGENT]]
        return selected

    def _select_by_intent(self, message: str, tokens: set[str], enabled_by_name: dict[str, dict]) -> list[dict]:
        selected_names: list[str] = []
        if self._has_creation_intent(message, tokens):
            is_document_or_content = bool(tokens & {"document", "doc", "content", "marketing", "post", "campaign", "calendar", "article", "essay"})
            if self._has_business_intent(tokens) and "Zeus" in enabled_by_name:
                selected_names.append("Zeus")
            if self._has_build_intent(message, tokens) and "Atlas" in enabled_by_name:
                selected_names.append("Atlas")
            if is_document_or_content and "Friday" in enabled_by_name:
                selected_names.append("Friday")
            if (tokens & {"study", "notes", "exam", "revision", "timetable"}) and "Alex" in enabled_by_name:
                selected_names.append("Alex")
            if not selected_names and "Friday" in enabled_by_name:
                selected_names.append("Friday")
            if self._has_explicit_research_intent(message, tokens) and "Nova" in enabled_by_name:
                selected_names.insert(0, "Nova")
            elif not is_document_or_content and tokens & {"startup", "market", "healthcare", "saas"} and "Nova" in enabled_by_name:
                selected_names.insert(0, "Nova")
            return [enabled_by_name[name] for name in selected_names[:3]]
        if self._has_research_intent(message, tokens) and "Nova" in enabled_by_name:
            selected_names.append("Nova")
        if self._has_research_only_intent(message, tokens):
            return [enabled_by_name[name] for name in selected_names]
        if self._has_business_intent(tokens) and "Zeus" in enabled_by_name:
            selected_names.append("Zeus")
        if self._has_build_intent(message, tokens) and "Atlas" in enabled_by_name:
            selected_names.append("Atlas")
        return [enabled_by_name[name] for name in selected_names[:3]]

    def _has_research_intent(self, message: str, tokens: set[str]) -> bool:
        if self._has_creation_intent(message, tokens) and not self._has_explicit_research_intent(message, tokens):
            return False
        return self._has_explicit_research_intent(message, tokens) or bool(tokens & {"sources", "competitors"})

    def _has_explicit_research_intent(self, message: str, tokens: set[str]) -> bool:
        research_phrases = [
            r"\bresearch\b",
            r"\bsearch\b",
            r"\bweb\s*search\b",
            r"\blook\s+up\b",
            r"\bcheck\s+(?:it|this|that|.+)\s+(?:on|in|using)\s+(?:the\s+)?web\b",
            r"\bcheck\s+(?:online|the internet|internet)\b",
            r"\bfind\s+(?:out|information|sources)\b",
        ]
        return any(re.search(pattern, message) for pattern in research_phrases) or bool(tokens & {"sources", "competitors"})

    def _has_research_only_intent(self, message: str, tokens: set[str]) -> bool:
        return self._has_research_intent(message, tokens) and not self._has_business_intent(tokens) and not self._has_build_intent(message, tokens)

    def _has_business_intent(self, tokens: set[str]) -> bool:
        return bool(tokens & {"business", "startup", "strategy", "growth", "revenue", "saas", "market"})

    def _has_creation_intent(self, message: str, tokens: set[str]) -> bool:
        if not (tokens & {"create", "write", "draft", "generate", "make", "prepare"}):
            return False
        return bool(tokens & {"document", "doc", "plan", "strategy", "content", "marketing", "post", "campaign", "deck", "report", "proposal", "notes", "timetable", "application", "resume", "letter"})

    def _is_healthcare_domain(self, message: str) -> bool:
        return bool(re.search(r"\bhealthcare\b|\bhealth\s*care\b|\bclinic(?:s)?\b|\bmedical\b|\bdigital health\b", message))

    def _is_memory_recall(self, message: str) -> bool:
        recall_patterns = [
            r"\bwhat (?:is|are|was|were)\s+(?:my|our|we)\b",
            r"\bwho (?:is|are|was|were)\s+(?:my|our|we)\b",
            r"\bwhere (?:do|are|did|will)\s+(?:i|we)\b",
            r"\bwhat .* called\b",
            r"\bdo you remember\b",
        ]
        action_patterns = [
            r"\bbuild\b",
            r"\bcreate\b",
            r"\bdevelop\b",
            r"\bdesign\b",
            r"\bimplement\b",
            r"\bstrategy\b",
            r"\bresearch\b",
        ]
        return any(re.search(pattern, message) for pattern in recall_patterns) and not any(
            re.search(pattern, message) for pattern in action_patterns
        )

    def _select_recall_agent(self, tokens: set[str], enabled_by_name: dict[str, dict]) -> list[dict]:
        if tokens & {"startup", "co", "founder", "launch", "business"} and "Zeus" in enabled_by_name:
            return [enabled_by_name["Zeus"]]
        if "Alex" in enabled_by_name:
            return [enabled_by_name["Alex"]]
        if DEFAULT_AGENT in enabled_by_name:
            return [enabled_by_name[DEFAULT_AGENT]]
        return list(enabled_by_name.values())[:1]

    def _has_build_intent(self, message: str, tokens: set[str]) -> bool:
        if re.search(r"\bwhat\s+are\s+we\s+building\b", message):
            return False
        return bool(tokens & {"build", "create", "develop", "code", "implement", "architect", "engineering", "technical"})
