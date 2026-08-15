from __future__ import annotations

from app.core.config.settings import settings

from .base import SandboxProvider, UnavailableSandboxProvider


def sandbox_provider() -> SandboxProvider:
    provider = settings.sandbox_provider.strip().lower()
    if provider == "docker":
        from .docker import DockerSandboxProvider
        return DockerSandboxProvider()
    return UnavailableSandboxProvider()
