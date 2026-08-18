from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

from sqlalchemy.orm import Session

from app.models.commercial import ResourcePolicyDecision
from app.services.capabilities.registry import capability_registry
from app.services.resource_policy_engine import PolicyDecision

LITE_BEHAVIOR_VERSION = "c8-v1"
ROLLOUT_MODES = {"observe", "selective_enforce", "full_enforce"}


@dataclass(frozen=True)
class LiteBehavior:
    capability_key: str
    lite_action: str
    fallback_capability: str | None = None
    max_compute: float | None = None
    message_key: str | None = None
    enabled: bool = True
    selective_enforce: bool = False
    version: str = LITE_BEHAVIOR_VERSION
    parameter_overrides: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class LiteExecutionResolution:
    requested_capability: str
    effective_capability: str
    lite_action: str
    requested_execution_mode: str
    effective_execution_mode: str
    should_execute: bool
    adapted_arguments: dict[str, Any]
    fallback_used: bool
    fallback_capability: str | None
    upgrade_prompted: bool
    response_key: str | None
    requires_confirmation: bool
    behavior_version: str
    rollout_mode: str


class LiteBehaviorRegistry:
    def __init__(self) -> None:
        self._behaviors = {item.capability_key: item for item in self._defaults()}

    def register(self, behavior: LiteBehavior) -> None:
        self._behaviors[behavior.capability_key] = behavior

    def resolve(self, capability_key: str) -> LiteBehavior | None:
        canonical = capability_registry.resolve_manifest(capability_key).key
        return self._behaviors.get(canonical)

    @staticmethod
    def _defaults() -> list[LiteBehavior]:
        full = (
            "applications.open", "applications.focus", "applications.close", "windows.controls",
            "files.list_directory", "files.read", "files.write", "files.delete",
            "browser.control", "browser.upload", "clipboard.read", "clipboard.write",
            "notifications.show", "device.sync", "automation.run", "document.create_file",
            "workforce.artifact_render",
        )
        values = [LiteBehavior(key, "FULL", selective_enforce=True) for key in full]
        values += [
            LiteBehavior("voice.simple_command", "LOCAL_ONLY", selective_enforce=True),
            LiteBehavior("github.list_issues", "PLUGIN_ONLY", selective_enforce=True),
            LiteBehavior("github.create_issue", "PLUGIN_ONLY", selective_enforce=True),
            LiteBehavior("notion.read_page", "PLUGIN_ONLY", selective_enforce=True),
            LiteBehavior("notion.update_page", "PLUGIN_ONLY", selective_enforce=True),
            LiteBehavior("web.search", "LIMITED_OUTPUT", max_compute=1, message_key="lite.web_search_limited", selective_enforce=True, parameter_overrides={"search_count": 1}),
            LiteBehavior("document.generate_content", "LIMITED_OUTPUT", fallback_capability="document.create_file", max_compute=5, message_key="lite.ai_generation_limited", selective_enforce=True, parameter_overrides={"max_output_tokens": 512}),
            LiteBehavior("voice.ai_conversation", "REDUCED_AI", max_compute=2, message_key="lite.compute_exhausted", selective_enforce=True, parameter_overrides={"max_output_tokens": 256}),
            LiteBehavior("workforce.run_job", "UPGRADE_REQUIRED", message_key="lite.workforce_upgrade_required", selective_enforce=True),
        ]
        return values


class LiteExecutionResolver:
    """Adapts an execution request and returns it to the existing executor."""

    def __init__(self, db: Session, registry: LiteBehaviorRegistry | None = None):
        self.db = db
        self.registry = registry or lite_behavior_registry

    def resolve(
        self, *, policy_decision: PolicyDecision, capability_key: str,
        arguments: Mapping[str, Any] | None = None, rollout_mode: str = "observe",
        request_context: Mapping[str, Any] | None = None,
    ) -> LiteExecutionResolution:
        if rollout_mode not in ROLLOUT_MODES:
            raise ValueError("unsupported Lite rollout mode")
        context, adapted = dict(request_context or {}), dict(arguments or {})
        manifest = capability_registry.resolve_manifest(capability_key)
        behavior = self.registry.resolve(manifest.key)
        enforce = rollout_mode == "full_enforce" or rollout_mode == "selective_enforce" and bool(behavior and behavior.selective_enforce)
        needs_lite = policy_decision.decision in {"ALLOW_LITE", "ALLOW_DEGRADED", "REQUIRE_UPGRADE", "DENY"}

        if not behavior or not behavior.enabled or not needs_lite or not enforce:
            resolution = LiteExecutionResolution(
                manifest.key, manifest.key, behavior.lite_action if behavior else "EXISTING_BEHAVIOR",
                policy_decision.execution_mode, "EXISTING_BEHAVIOR" if not enforce else "FULL",
                True, adapted, False, None, False, None,
                policy_decision.requires_confirmation, behavior.version if behavior else LITE_BEHAVIOR_VERSION, rollout_mode,
            )
            return self._record(policy_decision, resolution)

        action = behavior.lite_action
        effective, execute, fallback, upgrade, response_key = manifest.key, True, None, False, behavior.message_key
        mode = "FULL" if action == "FULL" else "LITE"
        if action in {"LOCAL_ONLY", "PLUGIN_ONLY"}:
            mode = "LITE"
        elif action == "LIMITED_OUTPUT":
            if manifest.key == "document.generate_content" and context.get("content_supplied"):
                effective, fallback = behavior.fallback_capability or manifest.key, behavior.fallback_capability
            else:
                adapted.update(behavior.parameter_overrides)
                if not context.get("limited_generation_available"):
                    execute, upgrade, mode = False, True, "UPGRADE_REQUIRED"
        elif action == "REDUCED_AI":
            adapted.update(behavior.parameter_overrides)
            if not context.get("reduced_ai_available"):
                execute, upgrade, mode = False, True, "UPGRADE_REQUIRED"
        elif action in {"UPGRADE_REQUIRED", "UNAVAILABLE", "QUEUE_NOT_ALLOWED"}:
            execute, upgrade, mode = False, action == "UPGRADE_REQUIRED", "UPGRADE_REQUIRED" if action == "UPGRADE_REQUIRED" else "BLOCKED"
        resolution = LiteExecutionResolution(
            manifest.key, effective, action, policy_decision.execution_mode, mode, execute, adapted,
            bool(fallback), fallback, upgrade, response_key,
            policy_decision.requires_confirmation, behavior.version, rollout_mode,
        )
        return self._record(policy_decision, resolution)

    def _record(self, decision: PolicyDecision, resolution: LiteExecutionResolution) -> LiteExecutionResolution:
        if decision.record_id:
            row = self.db.query(ResourcePolicyDecision).filter_by(id=decision.record_id).first()
            if row:
                row.requested_execution_mode = resolution.requested_execution_mode
                row.effective_execution_mode = resolution.effective_execution_mode
                row.fallback_used = resolution.fallback_used
                row.fallback_capability = resolution.fallback_capability
                row.upgrade_prompted = resolution.upgrade_prompted
                row.response_key = resolution.response_key
                row.lite_behavior_version = resolution.behavior_version
                row.rollout_mode = resolution.rollout_mode
                self.db.flush()
        return resolution


lite_behavior_registry = LiteBehaviorRegistry()
