from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator


class SandboxLimits(BaseModel):
    runtime_seconds: int = Field(default=900, ge=1)
    command_timeout_seconds: int = Field(default=120, ge=1)
    memory_mb: int = Field(default=512, ge=64)
    cpu_limit: float = Field(default=1.0, gt=0)
    disk_bytes: int = Field(default=104857600, ge=1024)
    pids_limit: int = Field(default=128, ge=16)
    max_output_bytes: int = Field(default=1048576, ge=1024)
    max_files: int = Field(default=5000, ge=1)


class SandboxHandle(BaseModel):
    sandbox_id: str
    provider: str
    workspace_path: str = "/workspace"
    metadata: dict[str, Any] = Field(default_factory=dict)


class SandboxCommand(BaseModel):
    argv: list[str] = Field(min_length=1, max_length=64)
    cwd: str = "."
    timeout_seconds: int | None = Field(default=None, ge=1)
    network_required: bool = False

    @field_validator("argv")
    @classmethod
    def validate_argv(cls, value: list[str]) -> list[str]:
        if any(not item or "\x00" in item or len(item) > 4096 for item in value):
            raise ValueError("Invalid command argument")
        return value


class SandboxCommandResult(BaseModel):
    status: Literal["completed", "failed", "timeout", "cancelled", "output_limit"]
    exit_code: int | None = None
    stdout: str = ""
    stderr: str = ""
    duration_ms: int = 0
    truncated: bool = False


class FileOperation(BaseModel):
    operation: Literal["mkdir", "write", "patch", "rename", "copy", "delete"]
    path: str
    destination: str | None = None
    content: str | None = None


class BoltCodingPlan(BaseModel):
    summary: str
    file_operations: list[FileOperation] = Field(default_factory=list, max_length=500)
    setup_commands: list[SandboxCommand] = Field(default_factory=list, max_length=20)
    build_commands: list[SandboxCommand] = Field(default_factory=list, max_length=10)
    test_commands: list[SandboxCommand] = Field(default_factory=list, max_length=10)


class SandboxManifest(BaseModel):
    provider: str
    toolchains: dict[str, str] = Field(default_factory=dict)
    files_changed: list[str] = Field(default_factory=list)
    commands: list[dict[str, Any]] = Field(default_factory=list)
    build_verified: bool = False
    tests_verified: bool = False
    revision: str | None = None
