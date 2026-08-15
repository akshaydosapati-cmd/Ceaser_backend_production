from __future__ import annotations

import time
from uuid import uuid4

from sqlalchemy.orm import Session

from app.agents.v2 import DeviceCapabilityRequest
from app.models.integration import Integration
from app.models.user import User
from app.services.audit_service import AuditService
from app.services.device_gateway_service import DeviceGatewayService
from app.services.integrations.provider_registry import ProviderRegistry


class GitHubProjectService:
    """Moves bounded non-secret project content through GitHub's API; credentials remain server-side."""

    def __init__(self, db: Session):
        self.db = db
        self.gateway = DeviceGatewayService(db)
        self.provider = ProviderRegistry().get("github")

    def execute(self, user: User, *, action: str, device_id: str, project: dict, confirmed: bool, repository: str | None = None, private: bool = True, task_id: str | None = None) -> dict:
        if not confirmed:
            return {"status": "confirmation_required", "error": "confirmation_required"}
        integration = self.db.query(Integration).filter(Integration.user_id == user.id, Integration.provider == "github").first()
        if not integration or integration.status != "connected":
            return {"status": "failed", "error": "github_not_connected"}
        task_id = task_id or f"github_{uuid4().hex}"
        if action == "create":
            metadata = self._device(user, device_id, "project.metadata", project, task_id)
            if metadata.get("status") != "completed":
                return metadata
            resolved = (((metadata.get("result") or {}).get("output") or {}).get("project") or {})
            project = {**project, **resolved}
            self._event(user.id, "project.resolved", task_id, project, {"status": "completed"})
            result = self._safe_call(lambda: self.provider.create_repository(integration, name=repository or project.get("display_name"), private=private))
            if result.get("status") == "completed":
                repo = result["data"]["repository"]
                self._event(user.id, "github.repository_created", task_id, project, {"repository": repo.get("full_name"), "visibility": result["data"].get("visibility")})
                self._set_remote(user, device_id, project, repo.get("url"), task_id)
            return result
        if action in {"push", "commit_push"}:
            if action == "commit_push":
                status = self._device(user, device_id, "git.status", project, task_id)
                self._event(user.id, "git.status", task_id, project, {"status": status.get("status")})
                if status.get("status") != "completed":
                    return status
                staged = self._device(user, device_id, "git.add", {**project, "paths": ["."]}, task_id)
                if staged.get("status") != "completed":
                    return staged
                committed = self._device(user, device_id, "git.commit", {**project, "message": "Update from CEASER"}, task_id)
                if committed.get("status") != "completed":
                    return committed
                self._event(user.id, "git.commit_created", task_id, project, {"status": "completed"})
            self._event(user.id, "github.push_started", task_id, project, {})
            exported = self._device(user, device_id, "project.export_files", project, task_id)
            if exported.get("status") != "completed":
                self._event(user.id, "github.push_failed", task_id, project, {"category": exported.get("error") or "unknown"})
                return exported
            output = ((exported.get("result") or {}).get("output") or {})
            project = {**project, **(output.get("project") or {})}
            self._event(user.id, "project.resolved", task_id, project, {"status": "completed"})
            full_name = repository or self._repository_from_project(project)
            result = self._safe_call(lambda: self.provider.push_files(integration, repository=full_name, files=output.get("files") or [], branch="main", message=f"CEASER update {task_id}"))
            self._event(user.id, "github.push_completed" if result.get("status") == "completed" else "github.push_failed", task_id, project, {"category": result.get("error"), "files": (result.get("data") or {}).get("files_updated", 0)})
            return result
        return {"status": "failed", "error": "unknown"}

    def _device(self, user, device_id, capability, arguments, task_id):
        request_id = f"github_device_{uuid4().hex}"
        command = self.gateway.submit(user, DeviceCapabilityRequest(
            request_id=request_id, task_id=task_id, agent_id="bolt", device_id=device_id, capability=capability,
            arguments=arguments, confirmation_requirement="already_confirmed", timeout_seconds=60, authorization={"user_id": user.id},
        ))
        deadline = time.monotonic() + 60
        while time.monotonic() < deadline:
            self.db.expire_all(); command = self.gateway.owned_command(user, request_id)
            if command and command.status in {"COMPLETED", "FAILED", "TIMEOUT", "CANCELLED"}:
                return {"status": command.status.lower(), "result": command.result_json, "error": command.safe_error}
            time.sleep(0.1)
        return {"status": "timeout", "error": "network_error"}

    def _set_remote(self, user, device_id, project, url, task_id):
        if url:
            self._device(user, device_id, "git.set_remote", {**project, "remote_url": url}, task_id)

    @staticmethod
    def _repository_from_project(project):
        remote = str(project.get("git_repository") or "")
        if "github.com/" not in remote:
            raise ValueError("repository_not_found")
        return remote.split("github.com/", 1)[1].removesuffix(".git").strip("/")

    def _event(self, user_id, action, task_id, project, metadata):
        AuditService(self.db).record(user_id=user_id, action=action, resource_type="bolt_project", resource_id=project.get("project_id"), metadata={"task_id": task_id, "project_id": project.get("project_id"), **{k: v for k, v in metadata.items() if v is not None}})

    @staticmethod
    def _safe_call(callback):
        try:
            return {"status": "completed", "data": callback()}
        except PermissionError:
            return {"status": "failed", "error": "github_unauthorized"}
        except ValueError as exc:
            code = str(exc); allowed = {"repository_exists", "repository_not_found", "remote_conflict", "push_rejected", "branch_conflict", "github_unauthorized", "invalid_project_export"}
            return {"status": "failed", "error": code if code in allowed else "unknown"}
        except Exception as exc:
            status = getattr(getattr(exc, "response", None), "status_code", None)
            code = "rate_limit" if status == 429 else "authentication" if status in {401, 403} else "network_error" if type(exc).__name__ in {"ConnectError", "TimeoutException"} else "unknown"
            return {"status": "failed", "error": code}
