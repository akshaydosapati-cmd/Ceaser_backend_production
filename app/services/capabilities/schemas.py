from __future__ import annotations

from dataclasses import dataclass, field

from app.agents.v2.models import ExecutionTarget


@dataclass(frozen=True)
class CapabilitySurface:
    chat: bool = True
    voice: bool = True
    desktop_overlay: bool = False
    automation: bool = False
    integrations: bool = False


@dataclass(frozen=True)
class Capability:
    id: str
    name: str
    owner_agent: str
    category: str
    description: str
    triggers: tuple[str, ...]
    surfaces: CapabilitySurface = field(default_factory=CapabilitySurface)
    overlay_mode: str = "compact"
    requires_confirmation: bool = False
    requires_connected_account: bool = False
    allowed_execution_targets: tuple[ExecutionTarget, ...] = (ExecutionTarget.NONE,)

    def as_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "owner_agent": self.owner_agent,
            "category": self.category,
            "description": self.description,
            "triggers": list(self.triggers),
            "surfaces": {
                "chat": self.surfaces.chat,
                "voice": self.surfaces.voice,
                "desktop_overlay": self.surfaces.desktop_overlay,
                "automation": self.surfaces.automation,
                "integrations": self.surfaces.integrations,
            },
            "overlay_mode": self.overlay_mode,
            "requires_confirmation": self.requires_confirmation,
            "requires_connected_account": self.requires_connected_account,
            "allowed_execution_targets": [target.value for target in self.allowed_execution_targets],
        }


@dataclass(frozen=True)
class CapabilityManifest:
    key: str
    name: str
    category: str
    description: str
    execution_type: str
    cost_class: str
    risk_level: str
    requires_ai: bool = False
    requires_web: bool = False
    requires_voice: bool = False
    requires_plugin: bool = False
    requires_network: bool = False
    local_execution_available: bool = False
    lite_allowed: bool = False
    estimated_latency_class: str = "instant"
    enabled: bool = True
    manifest_version: int = 1
    aliases: tuple[str, ...] = ()
    metadata: dict = field(default_factory=dict)

    def as_dict(self) -> dict:
        return {
            "key": self.key, "name": self.name, "category": self.category,
            "description": self.description, "execution_type": self.execution_type,
            "cost_class": self.cost_class, "risk_level": self.risk_level,
            "requires_ai": self.requires_ai, "requires_web": self.requires_web,
            "requires_voice": self.requires_voice, "requires_plugin": self.requires_plugin,
            "requires_network": self.requires_network,
            "local_execution_available": self.local_execution_available,
            "lite_allowed": self.lite_allowed,
            "estimated_latency_class": self.estimated_latency_class,
            "enabled": self.enabled, "manifest_version": self.manifest_version,
            "aliases": list(self.aliases), "metadata": dict(self.metadata),
        }
