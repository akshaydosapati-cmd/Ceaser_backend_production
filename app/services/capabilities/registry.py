from __future__ import annotations

from app.services.capabilities.schemas import Capability, CapabilitySurface
from app.agents.v2.models import ExecutionTarget


class CapabilityRegistry:
    """Single source of truth for CEASER abilities across chat, voice, desktop, and automations."""

    def __init__(self) -> None:
        self._capabilities = {capability.id: capability for capability in self._default_capabilities()}

    def list(self) -> list[Capability]:
        return list(self._capabilities.values())

    def get(self, capability_id: str) -> Capability | None:
        return self._capabilities.get(capability_id)

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
                allowed_execution_targets=(ExecutionTarget.NONE,),
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
                allowed_execution_targets=(ExecutionTarget.NONE,),
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
                allowed_execution_targets=(ExecutionTarget.NONE,),
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
                allowed_execution_targets=(ExecutionTarget.NONE, ExecutionTarget.CLOUD),
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
                allowed_execution_targets=(ExecutionTarget.NONE, ExecutionTarget.CLOUD),
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
                allowed_execution_targets=(ExecutionTarget.DEVICE, ExecutionTarget.CLOUD),
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
                allowed_execution_targets=(ExecutionTarget.DEVICE,),
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
                allowed_execution_targets=(ExecutionTarget.CLOUD,),
            ),
            Capability(
                id="desktop.open_application", name="Open Application", owner_agent="CEASER", category="desktop",
                description="Open an installed application on an authorized desktop.", triggers=("open chrome", "open calculator", "launch app"),
                surfaces=CapabilitySurface(chat=False, voice=True, desktop_overlay=True),
                allowed_execution_targets=(ExecutionTarget.DEVICE,),
            ),
            Capability(
                id="media.pause", name="Pause Media", owner_agent="CEASER", category="media",
                description="Pause media in the active Windows session.", triggers=("pause music", "pause media"),
                surfaces=CapabilitySurface(chat=False, voice=True, desktop_overlay=True),
                allowed_execution_targets=(ExecutionTarget.DEVICE,),
            ),
            Capability(
                id="strategy.reason", name="Strategy Reasoning", owner_agent="Zeus", category="strategy",
                description="Reason about strategy without external execution.", triggers=("plan strategy",),
                allowed_execution_targets=(ExecutionTarget.NONE,),
            ),
            Capability(
                id="project.build", name="Project Build", owner_agent="Bolt", category="project",
                description="Build a project where its working copy is available.", triggers=("build project", "run build"),
                allowed_execution_targets=(ExecutionTarget.DEVICE, ExecutionTarget.CLOUD),
            ),
            *self._local_development_capabilities(),
            *self._browser_capabilities(),
            Capability(
                id="cloud.workspace.build", name="Cloud Workspace Build", owner_agent="Bolt", category="cloud",
                description="Build in a CEASER cloud workspace when Stage 24 workers are available.", triggers=("cloud build",),
                allowed_execution_targets=(ExecutionTarget.CLOUD,),
            ),
        ]

    @staticmethod
    def _local_development_capabilities() -> list[Capability]:
        protected = {"project.delete", "git.commit", "github.create_repository", "github.push"}
        definitions = {
            "project.create": "Create a persistent project on an authorized desktop.", "project.open": "Register an authorized existing project.",
            "project.inspect": "Inspect bounded non-secret project context.", "project.list": "List registered local projects.",
            "project.exists": "Verify a local project exists.", "project.metadata": "Read safe project metadata.",
            "project.list_files": "List safe project files.", "project.export_files": "Export bounded non-secret project files for an authorized integration operation.", "project.read_file": "Read a non-secret project file.",
            "project.write_file": "Write a project-scoped file.", "project.patch_file": "Apply a conflict-aware project patch.",
            "project.create_directory": "Create a project-scoped directory.", "project.rename": "Rename project content.",
            "project.copy": "Copy project content.", "project.delete": "Delete project content after confirmation.",
            "project.stat": "Read safe project file metadata.", "project.test": "Run applicable project tests.",
            "terminal.run_scoped": "Run an allowlisted argv command inside a project.", "toolchain.discover": "Discover local development toolchains.",
            "git.init": "Initialize project Git metadata.", "git.status": "Read project Git status.",
            "git.diff": "Read a bounded project Git diff.", "git.add": "Stage project files.",
            "git.commit": "Create a checkpoint commit after confirmation.", "git.log": "Read recent revisions.", "git.set_remote": "Configure a credential-free project GitHub remote.",
            "vscode.open_project": "Open the exact project in VS Code.", "development.cancel": "Cancel an active local Bolt process tree.",
            "bolt.execute_plan": "Execute a validated Bolt coding plan on an authorized desktop.",
        }
        return [Capability(
            id=identifier, name=identifier.replace(".", " ").title(), owner_agent="Bolt", category=identifier.split(".", 1)[0],
            description=description, triggers=(identifier.replace(".", " "),),
            surfaces=CapabilitySurface(chat=True, voice=True, desktop_overlay=True), requires_confirmation=identifier in protected,
            allowed_execution_targets=(ExecutionTarget.DEVICE,),
        ) for identifier, description in definitions.items()]

    @staticmethod
    def _browser_capabilities() -> list[Capability]:
        protected = {"browser.upload"}
        definitions = {
            "browser.start": "Start the user's managed local browser session.", "browser.navigate": "Navigate to a validated web URL.",
            "browser.current_page": "Read the active browser page identity.", "browser.inspect": "Inspect bounded visible page structure.",
            "browser.find": "Find visible page content.", "browser.click": "Click one semantically identified page element.",
            "browser.type": "Type non-sensitive text into a page field.", "browser.select": "Select a page field option.",
            "browser.check": "Check a page option.", "browser.uncheck": "Uncheck a page option.", "browser.scroll": "Scroll the active page.",
            "browser.hover": "Hover one page element.", "browser.wait": "Wait for bounded page processing.",
            "browser.upload": "Upload an explicitly authorized local file.", "browser.download": "Download an inert file to the safe download directory.",
            "browser.back": "Navigate backward.", "browser.forward": "Navigate forward.", "browser.reload": "Reload the active page.",
            "browser.tabs": "List managed browser tabs.", "browser.open_tab": "Open a managed browser tab.", "browser.close_tab": "Close a managed browser tab.",
            "browser.screenshot": "Capture the managed page for local verification.", "browser.extract": "Extract bounded visible page information.",
            "browser.verify": "Verify a browser goal from bounded page state.", "browser.cancel": "Cancel a browser task.",
        }
        return [Capability(
            id=identifier, name=identifier.replace(".", " ").title(), owner_agent="Friday", category="browser",
            description=description, triggers=(identifier.replace(".", " "),),
            surfaces=CapabilitySurface(chat=True, voice=True, desktop_overlay=True), requires_confirmation=identifier in protected,
            allowed_execution_targets=(ExecutionTarget.DEVICE,),
        ) for identifier, description in definitions.items()]


capability_registry = CapabilityRegistry()
