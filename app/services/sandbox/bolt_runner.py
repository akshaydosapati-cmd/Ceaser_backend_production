from __future__ import annotations

import json
import re
import time
from typing import TYPE_CHECKING
from typing import Any

from app.agents.v2.orchestrator import AgentOrchestrator
from app.agents.v2.registry import AgentRegistry
from app.core.config.settings import settings
from app.intelligence.ai.model_router import request_for_agent
from app.intelligence.ai.sync import generate_text_sync
from app.models.cloud_runtime import CloudJob
from app.models.mixins import utc_now

if TYPE_CHECKING:
    from app.services.cloud_runtime.queue import DurableCloudQueue
    from app.services.cloud_runtime.service import CloudExecutionService

from .base import SandboxProvider
from .models import BoltCodingPlan, SandboxCommand, SandboxLimits, SandboxManifest
from .paths import confined_path
from .workspace import DurableSandboxWorkspace


class BoltCloudCodingRunner:
    def __init__(self, provider: SandboxProvider):
        self.provider = provider

    def run(self, job: CloudJob, service: CloudExecutionService, queue: DurableCloudQueue) -> None:
        if job.agent_id.lower() != "bolt" or job.execution_target != "CLOUD":
            raise ValueError("invalid_bolt_cloud_placement")
        limits = SandboxLimits(
            runtime_seconds=settings.cloud_job_max_runtime_seconds,
            command_timeout_seconds=settings.sandbox_command_timeout_seconds,
            memory_mb=settings.sandbox_memory_mb, cpu_limit=settings.sandbox_cpu_limit,
            disk_bytes=settings.cloud_workspace_max_bytes, pids_limit=settings.sandbox_pids_limit,
            max_output_bytes=settings.sandbox_max_output_bytes, max_files=settings.sandbox_max_files,
        )
        handle = None
        workspace = DurableSandboxWorkspace(service.db)
        logs: list[str] = []
        changed: list[str] = []
        exported = False
        self._deadline = time.monotonic() + limits.runtime_seconds
        try:
            handle = self.provider.create(owner_id=job.user_id, job_id=job.id, limits=limits)
            service.event(job, "sandbox.created", {"provider": self.provider.name})
            restored = workspace.restore(job, self.provider, handle)
            service.event(job, "sandbox.ready", {"restored": bool(restored)})
            service.checkpoint(job, self._next_step(service, job), {"status": "sandbox_ready", "restored_artifact_id": restored.id if restored else None})
            project_context = self._inspect(handle)
            plan = self._plan(job, restored=bool(restored), project_context=project_context)
            service.event(job, "bolt.project_initialized", {"continued": bool(restored), "operation_count": len(plan.file_operations)})
            self._apply_files(handle, plan, changed)
            service.event(job, "bolt.files_changed", {"count": len(changed), "paths": changed[:100]})
            service.checkpoint(job, self._next_step(service, job), {"status": "files_changed", "files": changed[:100]})
            self._durable_milestone(workspace, job, service, handle, changed, "initial_project_created")

            for command in plan.setup_commands:
                result = self._command(job, service, queue, handle, command, logs)
                if result.status != "completed":
                    raise ValueError("dependency_setup_failed")
            if plan.setup_commands:
                service.event(job, "bolt.dependencies_installed", {"commands": len(plan.setup_commands)})
                service.checkpoint(job, self._next_step(service, job), {"status": "dependencies_ready"})
                self._durable_milestone(workspace, job, service, handle, changed, "dependency_setup_complete")

            build_ok = self._verify(job, service, queue, handle, plan.build_commands, logs, "build")
            tests_ok = self._verify(job, service, queue, handle, plan.test_commands, logs, "tests") if plan.test_commands else True
            if not plan.build_commands or not build_ok or not tests_ok:
                repaired = self._repair(job, service, queue, handle, plan, logs, changed)
                build_ok, tests_ok = repaired if repaired else (build_ok, tests_ok)
            verified = bool(plan.build_commands and build_ok and tests_ok)
            if build_ok:
                self._durable_milestone(workspace, job, service, handle, changed, "build_passed")

            revision = self._git_checkpoint(handle, job, service, queue, logs) if verified else None
            manifest = SandboxManifest(
                provider=self.provider.name, toolchains=self.provider.toolchains(handle), files_changed=changed,
                commands=[{"line": line[:300]} for line in logs[-100:]], build_verified=build_ok,
                tests_verified=tests_ok, revision=revision,
            )
            service.event(job, "sandbox.export_started", {"milestone": "final"})
            artifacts = workspace.persist(job, self.provider, handle, manifest)
            exported = True
            log_artifact = workspace.persist_log(job, "build-test.log", "\n".join(logs).encode("utf-8")[: settings.cloud_artifact_max_bytes])
            for artifact in [*artifacts, log_artifact]:
                service.event(job, "cloud.artifact.created", {"artifact_id": artifact.id, "type": artifact.artifact_type})
            service.event(job, "sandbox.export_completed", {"artifact_count": len(artifacts) + 1})
            service.checkpoint(job, self._next_step(service, job), {
                "status": "verification_complete", "verified": verified, "revision": revision,
                "artifact_ids": [item.id for item in [*artifacts, log_artifact]],
            })
            if not verified:
                raise ValueError("build_verification_failed")
            job.result_summary = f"Bolt completed and verified the cloud project. {len(changed)} files changed."
            job.current_step, job.updated_at = "verified", utc_now()
            service.event(job, "bolt.verification_completed", {"verified": True, "build": build_ok, "tests": tests_ok})
            service.event(job, "execution.completed", {"verified": True})
            queue.acknowledge(job)
            service.event(job, "cloud.job.completed", {"verified": True})
            service.db.commit()
        except Exception:
            if handle and not exported:
                try:
                    archive = workspace.persist(job, self.provider, handle, SandboxManifest(provider=self.provider.name, files_changed=changed))
                    service.checkpoint(job, self._next_step(service, job), {"status": "failure_checkpoint", "artifact_ids": [item.id for item in archive]})
                except Exception:  # noqa: BLE001
                    pass
            raise
        finally:
            if handle:
                self.provider.destroy(handle)
                service.event(job, "sandbox.destroyed", {"provider": self.provider.name})
                service.db.commit()

    def _plan(self, job: CloudJob, *, restored: bool, project_context: dict | None = None) -> BoltCodingPlan:
        supplied = (job.arguments_json or {}).get("coding_plan")
        if supplied:
            return BoltCodingPlan.model_validate(supplied)
        prompt = str((job.arguments_json or {}).get("prompt") or (job.arguments_json or {}).get("command") or "Build the requested project.")
        definition = AgentRegistry().get("bolt")
        context = AgentOrchestrator().context_builder.build(definition, prompt, {
            "task_id": job.task_id, "active_project": {"id": str(job.workspace_id)},
            "execution_environment": {"target": "CLOUD", "restored_existing_project": restored},
            "existing_project": project_context or {},
        })
        request = request_for_agent("bolt", context_size_estimate=max(1, len(prompt) // 4))
        response = generate_text_sync(
            instructions=(
                f"{definition.instructions}\nReturn JSON only with summary, file_operations, setup_commands, build_commands, test_commands. "
                "File operations use operation/path/content/destination. Commands use argv arrays and optional cwd/timeout_seconds/network_required. "
                "Inspect and minimally modify an existing project when restored. Never use host paths, secrets, shell strings, or destructive host actions. "
                f"Bounded context: {context}"
            ),
            input_text=prompt, max_output_tokens=6000, model_request=request,
        )
        return BoltCodingPlan.model_validate(self._json(response))

    def _apply_files(self, handle, plan: BoltCodingPlan, changed: list[str]) -> None:
        for item in plan.file_operations:
            path = confined_path(item.path)
            if item.operation in {"write", "patch"}:
                self.provider.write_file(handle, path, (item.content or "").encode("utf-8"))
            else:
                self.provider.file_operation(handle, item.operation, path, item.destination)
            changed.append(path)
        if len(self.provider.list_files(handle)) > settings.sandbox_max_files:
            raise ValueError("file_limit_exceeded")

    def _command(self, job, service, queue, handle, command: SandboxCommand, logs: list[str]):
        if time.monotonic() >= self._deadline:
            service.event(job, "sandbox.resource_limit", {"limit": "runtime"})
            raise RuntimeError("timeout")
        service.event(job, "sandbox.command_started", {"argv0": command.argv[0], "job_id": job.id})
        state = {"checked_at": 0.0, "heartbeat_at": 0.0, "cancelled": False}
        result = self.provider.execute(handle, command, cancel_check=lambda: self._cancelled(service, job, queue, state))
        logs.append(f"$ {' '.join(command.argv)}\n{result.stdout}\n{result.stderr}"[: settings.sandbox_max_output_bytes])
        event = "sandbox.command_completed" if result.status == "completed" else "sandbox.command_failed"
        service.event(job, event, {"argv0": command.argv[0], "status": result.status, "exit_code": result.exit_code, "duration_ms": result.duration_ms})
        if result.status in {"timeout", "output_limit"}:
            service.event(job, "sandbox.resource_limit", {"limit": result.status})
        if result.status == "cancelled":
            service.event(job, "sandbox.cancelled", {})
            raise RuntimeError("job_cancelled")
        return result

    def _durable_milestone(self, workspace, job, service, handle, changed, milestone):
        service.event(job, "sandbox.export_started", {"milestone": milestone})
        artifacts = workspace.persist(job, self.provider, handle, SandboxManifest(provider=self.provider.name, files_changed=changed))
        service.event(job, "sandbox.export_completed", {"milestone": milestone, "artifact_ids": [item.id for item in artifacts]})
        service.checkpoint(job, self._next_step(service, job), {"status": milestone, "artifact_ids": [item.id for item in artifacts]})

    def _verify(self, job, service, queue, handle, commands, logs, kind):
        if kind == "build": service.event(job, "bolt.build_started", {"commands": len(commands)})
        for command in commands:
            result = self._command(job, service, queue, handle, command, logs)
            if result.status != "completed":
                service.event(job, f"bolt.{kind}_failed", {"exit_code": result.exit_code})
                return False
        if commands:
            service.event(job, "bolt.tests_passed" if kind == "tests" else "bolt.build_passed", {})
        return True

    def _repair(self, job, service, queue, handle, plan, logs, changed):
        for attempt in range(settings.sandbox_max_build_retries):
            repair_plans = (job.arguments_json or {}).get("repair_plans") or []
            service.event(job, "bolt.repair_started", {"attempt": attempt + 1})
            if attempt < len(repair_plans):
                repair = BoltCodingPlan.model_validate(repair_plans[attempt])
            else:
                repair = self._repair_plan(job, logs, self._inspect(handle))
            self._apply_files(handle, repair, changed)
            build = self._verify(job, service, queue, handle, repair.build_commands or plan.build_commands, logs, "build")
            tests = self._verify(job, service, queue, handle, repair.test_commands or plan.test_commands, logs, "tests") if (repair.test_commands or plan.test_commands) else True
            if build and tests:
                return build, tests
        return None

    def _repair_plan(self, job, logs, project_context):
        failure = "\n".join(logs[-4:])[-12000:]
        request = request_for_agent("bolt", context_size_estimate=max(1, (len(failure) + len(str(project_context))) // 4))
        response = generate_text_sync(
            instructions=(
                "You are Bolt repairing a failed cloud build inside an isolated workspace. Return JSON only using the existing "
                "BoltCodingPlan shape. Make the minimum file changes necessary and include build/test argv commands."
            ),
            input_text=f"Original task: {(job.arguments_json or {}).get('prompt', '')}\nExisting project: {project_context}\nFailure output: {failure}",
            max_output_tokens=5000, model_request=request,
        )
        return BoltCodingPlan.model_validate(self._json(response))

    def _inspect(self, handle):
        files = self.provider.list_files(handle)
        preferred = [name for name in files if re.search(r"(^|/)(package\.json|requirements\.txt|pyproject\.toml|README\.md|src/.+\.(?:js|jsx|ts|tsx|py|css|html))$", name, re.I)]
        contents = {}
        used = 0
        for name in preferred[:20]:
            try:
                raw = self.provider.read_file(handle, name)
            except Exception:  # noqa: BLE001
                continue
            if len(raw) > 25000 or used + len(raw) > 100000:
                continue
            contents[name] = raw.decode("utf-8", "replace")
            used += len(raw)
        return {"files": files[:500], "contents": contents, "truncated": len(files) > 500}

    def _git_checkpoint(self, handle, job, service, queue, logs):
        commands = [
            SandboxCommand(argv=["git", "init"]),
            SandboxCommand(argv=["git", "config", "user.name", "CEASER Bolt"]),
            SandboxCommand(argv=["git", "config", "user.email", "bolt@ceaser.local"]),
            SandboxCommand(argv=["git", "add", "-A"]),
            SandboxCommand(argv=["git", "commit", "-m", f"CEASER checkpoint {job.task_id}"]),
            SandboxCommand(argv=["git", "rev-parse", "HEAD"]),
        ]
        revision = None
        for command in commands:
            result = self._command(job, service, queue, handle, command, logs)
            if command.argv[:2] == ["git", "rev-parse"] and result.status == "completed":
                revision = result.stdout.strip()[:64]
        return revision

    @staticmethod
    def _cancelled(service, job, queue, state):
        now = time.monotonic()
        if now - state["checked_at"] < 1:
            return state["cancelled"]
        state["checked_at"] = now
        service.db.expire(job)
        service.db.refresh(job)
        if job.status == "CANCELLED":
            state["cancelled"] = True
            return True
        if now - state["heartbeat_at"] >= max(5, settings.cloud_worker_lease_seconds // 3):
            queue.heartbeat(job, job.claimed_by)
            state["heartbeat_at"] = now
        return False

    @staticmethod
    def _next_step(service, job):
        from app.models.cloud_runtime import CloudCheckpoint
        current = service.db.query(CloudCheckpoint).filter(CloudCheckpoint.job_id == job.id).count()
        return current + 1

    @staticmethod
    def _json(value: str) -> dict[str, Any]:
        text = str(value or "").strip()
        text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.IGNORECASE)
        start, end = text.find("{"), text.rfind("}")
        if start < 0 or end < start:
            raise ValueError("invalid_coding_plan")
        return json.loads(text[start:end + 1])
