from __future__ import annotations

from pathlib import PurePosixPath
import re

from .base import SandboxSecurityError


def confined_path(value: str) -> str:
    raw = str(value or "").replace("\\", "/").strip()
    path = PurePosixPath(raw)
    if not raw or path.is_absolute() or re.match(r"^[A-Za-z]:", raw) or ".." in path.parts or "\x00" in raw:
        raise SandboxSecurityError("workspace_path_rejected")
    normalized = str(path)
    if normalized in ("", "."):
        return "."
    return normalized


def workspace_path(value: str) -> str:
    relative = confined_path(value)
    return "/workspace" if relative == "." else f"/workspace/{relative}"
