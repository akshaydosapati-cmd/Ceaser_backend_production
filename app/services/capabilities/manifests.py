from __future__ import annotations

from app.services.capabilities.schemas import CapabilityManifest


def _manifest(key: str, category: str, execution: str, cost: str, risk: str, **values) -> CapabilityManifest:
    return CapabilityManifest(
        key=key, name=values.pop("name", key.replace(".", " ").title()), category=category,
        description=values.pop("description", f"CEASER capability: {key}."),
        execution_type=execution, cost_class=cost, risk_level=risk, **values,
    )


def core_manifests() -> list[CapabilityManifest]:
    """Version-controlled descriptions of user-visible CEASER behavior."""
    return [
        _manifest("chat.answer", "chat", "ai", "variable", "low", requires_ai=True, requires_network=True, lite_allowed=False, estimated_latency_class="medium", aliases=("ai.answer", "ai_conversation")),
        _manifest("voice.transcribe", "voice", "voice", "low", "low", requires_voice=True, requires_network=True, lite_allowed=True, estimated_latency_class="low"),
        _manifest("voice.intent", "voice", "hybrid", "negligible", "low", requires_voice=True, local_execution_available=True, lite_allowed=True, estimated_latency_class="instant"),
        _manifest("voice.synthesize", "voice", "voice", "low", "low", requires_voice=True, requires_network=True, lite_allowed=True, estimated_latency_class="low"),
        _manifest("voice.simple_command", "voice", "local", "free", "low", requires_voice=True, local_execution_available=True, lite_allowed=True, aliases=("local_command",)),
        _manifest("voice.ai_conversation", "voice", "hybrid", "variable", "low", requires_ai=True, requires_voice=True, requires_network=True, lite_allowed=False, estimated_latency_class="medium"),
        _manifest("applications.open", "applications", "local", "free", "low", local_execution_available=True, lite_allowed=True, aliases=("open_app", "launch_app", "windows.open_application", "desktop.open_application", "app.open")),
        _manifest("applications.focus", "applications", "local", "free", "low", local_execution_available=True, lite_allowed=True, aliases=("app.focus",)),
        _manifest("applications.close", "applications", "local", "free", "medium", local_execution_available=True, lite_allowed=True, aliases=("app.close",)),
        _manifest("windows.controls", "windows", "local", "free", "low", local_execution_available=True, lite_allowed=True, aliases=("audio.volume.set", "system.open_settings", "wifi.status", "window.resize", "window.move_to_monitor")),
        _manifest("files.list_directory", "files", "local", "free", "low", local_execution_available=True, lite_allowed=True, aliases=("project.list_files", "file.search")),
        _manifest("files.read", "files", "local", "free", "low", local_execution_available=True, lite_allowed=True, aliases=("project.read_file",)),
        _manifest("files.write", "files", "local", "free", "medium", local_execution_available=True, lite_allowed=True, aliases=("project.write_file", "project.patch_file", "directory.create")),
        _manifest("files.delete", "files", "local", "free", "high", local_execution_available=True, lite_allowed=True, aliases=("project.delete",)),
        _manifest("browser.control", "browser", "local", "free", "medium", local_execution_available=True, lite_allowed=True, aliases=("browser.navigate", "browser.click", "browser.type", "browser.tabs", "browser.open_tab", "browser.close_tab")),
        _manifest("browser.upload", "browser", "local", "free", "high", local_execution_available=True, lite_allowed=True),
        _manifest("clipboard.read", "clipboard", "local", "free", "medium", local_execution_available=True, lite_allowed=True),
        _manifest("clipboard.write", "clipboard", "local", "free", "medium", local_execution_available=True, lite_allowed=True),
        _manifest("notifications.show", "notifications", "local", "free", "low", local_execution_available=True, lite_allowed=True),
        _manifest("device.sync", "device", "hybrid", "negligible", "medium", requires_network=True, local_execution_available=True, lite_allowed=True),
        _manifest("github.list_issues", "github", "plugin", "negligible", "low", requires_plugin=True, requires_network=True, lite_allowed=True),
        _manifest("github.create_issue", "github", "plugin", "negligible", "medium", requires_plugin=True, requires_network=True, lite_allowed=True),
        _manifest("github.analyze_repository", "github", "hybrid", "variable", "low", requires_ai=True, requires_plugin=True, requires_network=True, lite_allowed=False, estimated_latency_class="medium"),
        _manifest("notion.read_page", "notion", "plugin", "negligible", "low", requires_plugin=True, requires_network=True, lite_allowed=True),
        _manifest("notion.update_page", "notion", "plugin", "negligible", "medium", requires_plugin=True, requires_network=True, lite_allowed=True),
        _manifest("notion.summarize_workspace", "notion", "hybrid", "variable", "low", requires_ai=True, requires_plugin=True, requires_network=True, lite_allowed=False, estimated_latency_class="medium"),
        _manifest("web.search", "web", "web", "low", "low", requires_web=True, requires_network=True, lite_allowed=True, estimated_latency_class="low", aliases=("research", "web_search")),
        _manifest("document.create_file", "document", "artifact", "negligible", "low", local_execution_available=True, lite_allowed=True, aliases=("document.create",)),
        _manifest("document.generate_content", "document", "ai", "variable", "low", requires_ai=True, requires_network=True, lite_allowed=False, estimated_latency_class="medium"),
        _manifest("presentation.create", "artifact", "hybrid", "variable", "low", requires_ai=True, requires_network=True, lite_allowed=False, estimated_latency_class="medium"),
        _manifest("workforce.plan", "workforce", "ai", "variable", "low", requires_ai=True, requires_network=True, lite_allowed=False, estimated_latency_class="medium"),
        _manifest("workforce.agent_call", "workforce", "ai", "variable", "low", requires_ai=True, requires_network=True, lite_allowed=False, estimated_latency_class="medium"),
        _manifest("workforce.web_research", "workforce", "hybrid", "variable", "low", requires_ai=True, requires_web=True, requires_network=True, lite_allowed=False, estimated_latency_class="high"),
        _manifest("workforce.artifact_render", "workforce", "artifact", "negligible", "low", local_execution_available=True, lite_allowed=True),
        _manifest("workforce.execute_plugin", "workforce", "plugin", "variable", "medium", requires_plugin=True, requires_network=True, lite_allowed=False),
        _manifest("workforce.run_job", "workforce", "workforce", "high", "medium", requires_ai=True, requires_network=True, lite_allowed=False, estimated_latency_class="high", aliases=("agent_workflow", "bolt.execution")),
        _manifest("automation.run", "automation", "hybrid", "variable", "medium", requires_network=True, local_execution_available=True, lite_allowed=True),
    ]
