from __future__ import annotations

from app.services.capabilities.schemas import Capability, CapabilitySurface


class CapabilityRegistry:
    """Single source of truth for CEASER abilities across chat, voice, desktop, and automations."""

    def __init__(self) -> None:
        self._capabilities = {capability.id: capability for capability in self._default_capabilities()}

    def list(self) -> list[Capability]:
        return list(self._capabilities.values())

    def by_agent(self, agent: str) -> list[Capability]:
        key = agent.lower()
        return [capability for capability in self.list() if capability.owner_agent.lower() == key]

    def by_surface(self, surface: str) -> list[Capability]:
        return [capability for capability in self.list() if bool(getattr(capability.surfaces, surface, False))]

    def match(self, text: str) -> Capability | None:
        normalized = text.lower()
        ranked: list[tuple[int, Capability]] = []
        for capability in self.list():
            score = sum(1 for trigger in capability.triggers if trigger in normalized)
            if score:
                ranked.append((score, capability))
        if not ranked:
            return None
        ranked.sort(key=lambda item: item[0], reverse=True)
        return ranked[0][1]

    def _default_capabilities(self) -> list[Capability]:
        return [
            Capability(
                id="nova.deep_research",
                name="Deep Research",
                owner_agent="Nova",
                category="research",
                description="Multi-source research, competitor discovery, news, market scans, and citation-backed briefs.",
                triggers=("research", "sources", "competitor", "market", "trend", "news", "latest"),
                surfaces=CapabilitySurface(chat=True, voice=True, desktop_overlay=True, automation=True, integrations=True),
                overlay_mode="expanded",
                requires_connected_account=False,
            ),
            Capability(
                id="zeus.strategy",
                name="Business Strategy",
                owner_agent="Zeus",
                category="strategy",
                description="Startup strategy, pitch decks, GTM plans, revenue models, SWOT, and investor narratives.",
                triggers=("strategy", "business", "growth", "revenue", "pitch", "gtm", "investor"),
                surfaces=CapabilitySurface(chat=True, voice=True, desktop_overlay=True, automation=True),
                overlay_mode="expanded",
            ),
            Capability(
                id="atlas.technical_planning",
                name="Technical Planning",
                owner_agent="Atlas",
                category="technical",
                description="Architecture, technical roadmaps, code explanation, API plans, and engineering documentation.",
                triggers=("architecture", "technical", "api", "software", "code", "repository"),
                surfaces=CapabilitySurface(chat=True, voice=True, desktop_overlay=True, automation=False),
                overlay_mode="expanded",
            ),
            Capability(
                id="friday.content",
                name="Content Operations",
                owner_agent="Friday",
                category="content",
                description="LinkedIn posts, content calendars, campaign plans, scripts, and marketing documents.",
                triggers=("content", "campaign", "linkedin", "social", "calendar", "marketing"),
                surfaces=CapabilitySurface(chat=True, voice=True, desktop_overlay=True, automation=True, integrations=True),
                overlay_mode="expanded",
            ),
            Capability(
                id="alex.study",
                name="Study Companion",
                owner_agent="Alex",
                category="learning",
                description="Study plans, exam prep, notes, flashcards, MCQs, habit tracking, and learning reviews.",
                triggers=("study", "exam", "learn", "revision", "assignment", "classroom", "notes"),
                surfaces=CapabilitySurface(chat=True, voice=True, desktop_overlay=True, automation=True, integrations=True),
                overlay_mode="expanded",
            ),
            Capability(
                id="bolt.execution",
                name="Execution Planning",
                owner_agent="Bolt",
                category="execution",
                description="Tasks, roadmaps, deadlines, follow-ups, automation setup, and operational reviews.",
                triggers=("task", "execute", "launch", "workflow", "automation", "deadline", "follow up"),
                surfaces=CapabilitySurface(chat=True, voice=True, desktop_overlay=True, automation=True, integrations=True),
                overlay_mode="expanded",
            ),
            Capability(
                id="desktop.quick_actions",
                name="Desktop Quick Actions",
                owner_agent="CEASER",
                category="desktop",
                description="Open and close apps, websites, folders, files, clipboard, screenshots, and window actions.",
                triggers=("open", "close", "launch", "folder", "window", "clipboard", "screenshot"),
                surfaces=CapabilitySurface(chat=False, voice=True, desktop_overlay=True, automation=False),
                overlay_mode="compact",
                requires_confirmation=False,
            ),
            Capability(
                id="daily.digest",
                name="Daily Brief",
                owner_agent="CEASER",
                category="proactive",
                description="Morning agenda from memory, automations, integrations, recent activity, and priorities.",
                triggers=("daily brief", "morning brief", "good morning", "today agenda"),
                surfaces=CapabilitySurface(chat=True, voice=True, desktop_overlay=True, automation=True, integrations=True),
                overlay_mode="expanded",
                requires_connected_account=True,
            ),
        ]


capability_registry = CapabilityRegistry()
