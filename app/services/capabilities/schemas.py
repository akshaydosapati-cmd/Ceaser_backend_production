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
