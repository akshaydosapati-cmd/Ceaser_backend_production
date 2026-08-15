from __future__ import annotations

import base64
import hashlib
import json
import os
import subprocess
import tempfile
import time

from app.core.config.settings import settings

from .base import CancelCheck, SandboxProvider, SandboxSecurityError, SandboxUnavailableError
from .models import SandboxCommand, SandboxCommandResult, SandboxHandle, SandboxLimits
from .paths import confined_path, workspace_path


_FILE_SCRIPT = r"""
import base64, os, pathlib, shutil, sys
root = pathlib.Path('/workspace').resolve()
def safe(raw, allow_missing=True):
    candidate = root.joinpath(raw)
    parent = candidate.parent.resolve()
    resolved = candidate.resolve(strict=False)
    if root != resolved and root not in resolved.parents: raise SystemExit(73)
    if root != parent and root not in parent.parents: raise SystemExit(73)
    current = root
    for part in pathlib.PurePosixPath(raw).parts[:-1]:
        current = current / part
        if current.is_symlink(): raise SystemExit(73)
    return candidate
op, source = sys.argv[1], sys.argv[2]
path = safe(source)
if op == 'write':
    path.parent.mkdir(parents=True, exist_ok=True); path.write_bytes(base64.b64decode(sys.stdin.buffer.read()))
elif op == 'read':
    if path.is_symlink(): raise SystemExit(73)
    sys.stdout.buffer.write(path.read_bytes())
elif op == 'mkdir': path.mkdir(parents=True, exist_ok=True)
elif op == 'delete':
    if path.is_symlink() or path.is_file(): path.unlink(missing_ok=True)
    elif path.exists(): shutil.rmtree(path)
elif op in ('rename', 'copy'):
    target = safe(sys.argv[3]); target.parent.mkdir(parents=True, exist_ok=True)
    (path.rename(target) if op == 'rename' else (shutil.copytree(path, target) if path.is_dir() else shutil.copy2(path, target)))
elif op == 'stat':
    print(__import__('json').dumps({'exists': path.exists(), 'is_file': path.is_file(), 'is_dir': path.is_dir(), 'size': path.stat().st_size if path.exists() and path.is_file() else 0}))
"""


class DockerSandboxProvider(SandboxProvider):
    name = "docker"

    def __init__(self, *, image: str | None = None, network_mode: str | None = None):
        self.image = image or settings.sandbox_docker_image
        self.network_mode = network_mode or settings.sandbox_network_mode
        self.available = self._docker_available()

    @staticmethod
    def _docker_available() -> bool:
        try:
            result = subprocess.run(["docker", "version", "--format", "{{.Server.Version}}"], capture_output=True, timeout=5, check=False)
            return result.returncode == 0
        except (OSError, subprocess.SubprocessError):
            return False

    def create(self, *, owner_id: str, job_id: str, limits: SandboxLimits) -> SandboxHandle:
        if not self.available:
            raise SandboxUnavailableError("docker_unavailable")
        digest = hashlib.sha256(f"{owner_id}:{job_id}:{time.time_ns()}".encode()).hexdigest()[:20]
        name = f"ceaser-sbx-{digest}"
        network = self.network_mode if self.network_mode in {"none", "bridge"} else "none"
        args = [
            "docker", "create", "--name", name, "--network", network, "--read-only",
            "--tmpfs", "/tmp:rw,nosuid,nodev,noexec,size=64m",
            "--tmpfs", f"/workspace:rw,nosuid,nodev,mode=1777,size={limits.disk_bytes}",
            "--cap-drop", "ALL", "--security-opt", "no-new-privileges:true",
            "--pids-limit", str(limits.pids_limit), "--memory", f"{limits.memory_mb}m",
            "--cpus", str(limits.cpu_limit), "--user", "1000:1000", "--workdir", "/workspace",
            self.image, "sleep", "infinity",
        ]
        created = subprocess.run(args, capture_output=True, text=True, timeout=30, check=False)
        if created.returncode != 0:
            raise SandboxUnavailableError("sandbox_create_failed")
        started = subprocess.run(["docker", "start", name], capture_output=True, timeout=20, check=False)
        if started.returncode != 0:
            subprocess.run(["docker", "rm", "-f", name], capture_output=True, check=False)
            raise SandboxUnavailableError("sandbox_start_failed")
        return SandboxHandle(sandbox_id=name, provider=self.name, metadata={"network_mode": network, "image": self.image})

    def destroy(self, handle: SandboxHandle) -> None:
        subprocess.run(["docker", "rm", "-f", handle.sandbox_id], capture_output=True, timeout=20, check=False)

    def execute(self, handle: SandboxHandle, command: SandboxCommand, *, cancel_check: CancelCheck | None = None) -> SandboxCommandResult:
        cwd = workspace_path(command.cwd)
        timeout = min(command.timeout_seconds or settings.sandbox_command_timeout_seconds, settings.cloud_job_max_runtime_seconds)
        if command.network_required and self.network_mode == "none":
            return SandboxCommandResult(status="failed", stderr="Sandbox network policy blocks this command.", exit_code=77)
        started = time.perf_counter()
        limit = settings.sandbox_max_output_bytes
        with tempfile.TemporaryFile() as stdout_file, tempfile.TemporaryFile() as stderr_file:
            proc = subprocess.Popen(
                ["docker", "exec", "--workdir", cwd, handle.sandbox_id, *command.argv],
                stdout=stdout_file, stderr=stderr_file,
            )
            status = "completed"
            while proc.poll() is None:
                if os.fstat(stdout_file.fileno()).st_size + os.fstat(stderr_file.fileno()).st_size > limit:
                    subprocess.run(["docker", "kill", handle.sandbox_id], capture_output=True, check=False)
                    proc.terminate(); status = "output_limit"; break
                if cancel_check and cancel_check():
                    subprocess.run(["docker", "kill", handle.sandbox_id], capture_output=True, check=False)
                    proc.terminate(); status = "cancelled"; break
                if time.perf_counter() - started >= timeout:
                    subprocess.run(["docker", "kill", handle.sandbox_id], capture_output=True, check=False)
                    proc.terminate(); status = "timeout"; break
                time.sleep(0.1)
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill(); proc.wait(timeout=2)
            stdout_file.seek(0); stderr_file.seek(0)
            stdout, stderr = stdout_file.read(limit // 2), stderr_file.read(limit // 2)
            truncated = status == "output_limit" or os.fstat(stdout_file.fileno()).st_size + os.fstat(stderr_file.fileno()).st_size > limit
            if status == "completed" and proc.returncode:
                status = "failed"
        return SandboxCommandResult(
            status=status, exit_code=proc.returncode, stdout=stdout.decode("utf-8", "replace"), stderr=stderr.decode("utf-8", "replace"),
            duration_ms=int((time.perf_counter() - started) * 1000), truncated=truncated,
        )

    def _file(self, handle: SandboxHandle, operation: str, path: str, destination: str | None = None, stdin: bytes | None = None) -> bytes:
        source = confined_path(path)
        args = ["docker", "exec", "-i", handle.sandbox_id, "python3", "-c", _FILE_SCRIPT, operation, source]
        if destination is not None:
            args.append(confined_path(destination))
        result = subprocess.run(args, input=stdin, capture_output=True, timeout=30, check=False)
        if result.returncode == 73:
            raise SandboxSecurityError("workspace_symlink_escape_rejected")
        if result.returncode != 0:
            raise RuntimeError("sandbox_file_operation_failed")
        return result.stdout

    def write_file(self, handle: SandboxHandle, path: str, content: bytes) -> None:
        self._file(handle, "write", path, stdin=base64.b64encode(content))

    def read_file(self, handle: SandboxHandle, path: str) -> bytes:
        return self._file(handle, "read", path)

    def list_files(self, handle: SandboxHandle) -> list[str]:
        result = subprocess.run(
            ["docker", "exec", handle.sandbox_id, "find", "/workspace", "-type", "f", "-not", "-path", "*/.git/*"],
            capture_output=True, text=True, timeout=30, check=False,
        )
        if result.returncode != 0:
            raise RuntimeError("sandbox_list_failed")
        return [line.replace("/workspace/", "", 1) for line in result.stdout.splitlines() if line.startswith("/workspace/")][: settings.sandbox_max_files]

    def list_directory(self, handle: SandboxHandle, path: str = ".") -> list[str]:
        target = workspace_path(path)
        result = subprocess.run(
            ["docker", "exec", handle.sandbox_id, "find", target, "-mindepth", "1", "-maxdepth", "1", "-printf", "%f\n"],
            capture_output=True, text=True, timeout=30, check=False,
        )
        if result.returncode != 0:
            raise RuntimeError("sandbox_list_directory_failed")
        return sorted(result.stdout.splitlines())[: settings.sandbox_max_files]

    def stat(self, handle: SandboxHandle, path: str) -> dict:
        return json.loads(self._file(handle, "stat", path).decode("utf-8"))

    def file_operation(self, handle: SandboxHandle, operation: str, path: str, destination: str | None = None) -> None:
        if operation not in {"mkdir", "rename", "copy", "delete"}:
            raise SandboxSecurityError("unsupported_file_operation")
        self._file(handle, operation, path, destination)

    def export_archive(self, handle: SandboxHandle) -> bytes:
        result = subprocess.run(["docker", "exec", handle.sandbox_id, "tar", "-C", "/workspace", "-czf", "-", "."], capture_output=True, timeout=60, check=False)
        if result.returncode != 0:
            raise RuntimeError("sandbox_export_failed")
        if len(result.stdout) > settings.cloud_workspace_max_bytes:
            raise ValueError("workspace_too_large")
        return result.stdout

    def restore_archive(self, handle: SandboxHandle, archive: bytes) -> None:
        if len(archive) > settings.cloud_workspace_max_bytes:
            raise ValueError("workspace_too_large")
        result = subprocess.run(
            ["docker", "exec", "-i", handle.sandbox_id, "tar", "-C", "/workspace", "--no-same-owner", "--no-same-permissions", "-xzf", "-"],
            input=archive, capture_output=True, timeout=60, check=False,
        )
        if result.returncode != 0:
            raise RuntimeError("sandbox_restore_failed")

    def toolchains(self, handle: SandboxHandle) -> dict[str, str]:
        versions = {}
        for name, argv in {"node": ["node", "--version"], "npm": ["npm", "--version"], "python": ["python3", "--version"], "pip": ["pip", "--version"], "git": ["git", "--version"]}.items():
            result = self.execute(handle, SandboxCommand(argv=argv, timeout_seconds=10))
            if result.status == "completed":
                versions[name] = (result.stdout or result.stderr).strip().splitlines()[0][:120]
        return versions
