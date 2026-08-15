from __future__ import annotations

import hashlib
import logging
import time

from app.agents.v2.orchestrator import AgentOrchestrator
from app.agents.v2.registry import AgentRegistry
from app.core.config.settings import settings
from app.core.database.session import SessionLocal
from app.intelligence.ai.model_router import request_for_agent
from app.intelligence.ai.sync import generate_text_sync
from app.models.cloud_runtime import CloudArtifact, CloudJob
from app.models.mixins import utc_now
from app.services.capabilities.registry import capability_registry
from app.services.storage_service import StorageService
from app.services.sandbox import UnavailableSandboxProvider, sandbox_provider
from app.services.sandbox.bolt_runner import BoltCloudCodingRunner

from .queue import DurableCloudQueue
from .service import CloudExecutionService


logger = logging.getLogger(__name__)
RETRYABLE = {"network_error", "timeout", "rate_limit", "worker_interruption", "provider_unavailable"}
UNSAFE_BUILD_CAPABILITIES = {"project.build", "cloud.workspace.build"}


SandboxExecutor = UnavailableSandboxProvider


class CloudWorker:
    def __init__(self, worker_id: str | None = None, sandbox: SandboxExecutor | None = None):
        self.worker_id = worker_id or settings.cloud_worker_id
        self.sandbox = sandbox or sandbox_provider()
        self.running = False

    def run_once(self) -> bool:
        with SessionLocal() as db:
            queue = DurableCloudQueue(db, lease_seconds=settings.cloud_worker_lease_seconds)
            queue.release_stale()
            job = queue.claim_next(self.worker_id)
            if not job:
                return False
            service = CloudExecutionService(db)
            service.event(job, "cloud.job.claimed", {"worker_id": self.worker_id, "attempt": job.attempt_count})
            service.event(job, "cloud.job.started", {"worker_id": self.worker_id})
            db.commit()
            try:
                self._execute(job, service, queue)
            except Exception as exc:  # noqa: BLE001
                db.refresh(job)
                if job.status == "CANCELLED":
                    service.event(job, "cloud.job.cancelled", {"worker_observed": True})
                    db.commit()
                    return True
                category = self._category(exc)
                safe_error = self._safe_error(exc)
                queue.retry(job, category=category, safe_error=safe_error)
                service.event(job, "cloud.job.retrying" if job.status == "RETRYING" else "cloud.job.failed", {"category": category})
                db.commit()
            return True

    def serve_forever(self) -> None:
        self.running = True
        logger.info("cloud.worker.started worker_id=%s", self.worker_id)
        try:
            while self.running:
                if not self.run_once():
                    time.sleep(max(1, settings.cloud_worker_poll_seconds))
        finally:
            logger.info("cloud.worker.stopped worker_id=%s", self.worker_id)

    def stop(self) -> None:
        self.running = False

    def _execute(self, job: CloudJob, service: CloudExecutionService, queue: DurableCloudQueue) -> None:
        db = service.db
        db.refresh(job)
        if job.status == "CANCELLED":
            return
        capability = capability_registry.get(job.capability)
        if not capability or not any(target.value == "CLOUD" for target in capability.allowed_execution_targets):
            raise ValueError("unsupported_capability")
        if job.capability in UNSAFE_BUILD_CAPABILITIES and not self.sandbox.available:
            job.status = "WAITING_FOR_RESOURCE"
            job.failure_category = "sandbox_unavailable"
            job.safe_error = "An isolated cloud build sandbox is not configured."
            job.current_step = "waiting_for_sandbox"
            job.updated_at = utc_now()
            job.claimed_by = None
            job.lease_expires_at = None
            service.event(job, "cloud.job.waiting_for_resource", {"resource": "isolated_build_sandbox"})
            db.commit()
            return
        if not settings.supabase_url or not settings.supabase_service_role_key:
            job.status = "WAITING_FOR_RESOURCE"
            job.failure_category = "object_storage_unavailable"
            job.safe_error = "Durable object storage is not configured for the cloud worker."
            job.current_step = "waiting_for_object_storage"
            job.claimed_by = None
            job.lease_expires_at = None
            service.event(job, "cloud.job.waiting_for_resource", {"resource": "durable_object_storage"})
            db.commit()
            return

        if job.capability in UNSAFE_BUILD_CAPABILITIES:
            BoltCloudCodingRunner(self.sandbox).run(job, service, queue)
            return

        definition = AgentRegistry().get(job.agent_id)
        if not definition:
            raise ValueError("unknown_agent")
        job.status, job.current_step, job.progress = "PLANNING", "agent_planning", 0.1
        service.event(job, "agent.planning", {"agent_id": job.agent_id})
        service.checkpoint(job, 1, {"status": "plan_ready", "capability": job.capability})
        db.refresh(job)
        if job.status == "CANCELLED":
            return

        prompt = str((job.arguments_json or {}).get("prompt") or (job.arguments_json or {}).get("command") or "Complete the requested cloud task.")
        scoped_context = AgentOrchestrator().context_builder.build(
            definition, prompt, {"task_id": job.task_id, "active_project": {"id": str(job.workspace_id)}},
        )
        job.status, job.current_step, job.progress = "RUNNING", "model_generation", 0.35
        queue.heartbeat(job, self.worker_id)
        model_request = request_for_agent(job.agent_id, context_size_estimate=max(1, len(prompt) // 4))
        response = generate_text_sync(
            instructions=f"{definition.instructions}\nUse only this bounded cloud task context: {scoped_context}",
            input_text=prompt,
            max_output_tokens=1800,
            model_request=model_request,
        )
        from app.intelligence.ai.ai_provider_service import ai_provider_service
        selected = next((event for event in reversed(ai_provider_service.llm.router.events) if event.request_id == model_request.request_id and event.event == "model.selected"), None)
        if selected:
            service.event(job, "model.selected", {"model_id": selected.model_id, "provider_id": selected.provider_id})
        db.refresh(job)
        if job.status == "CANCELLED":
            return
        content = response.encode("utf-8")
        if len(content) > settings.cloud_artifact_max_bytes:
            raise ValueError("artifact_too_large")
        storage_key = StorageService().store(
            user_id=job.user_id, filename=f"cloud-{job.id}-result.md", content=content, content_type="text/markdown",
        )
        if storage_key.startswith("local://"):
            raise RuntimeError("durable_object_storage_unavailable")
        artifact = CloudArtifact(
            user_id=job.user_id, job_id=job.id, workspace_id=job.workspace_id, artifact_type="result",
            name="result.md", storage_key=storage_key, content_type="text/markdown", size_bytes=len(content),
            checksum=hashlib.sha256(content).hexdigest(), metadata_json={"agent_id": job.agent_id},
        )
        db.add(artifact)
        db.flush()
        service.event(job, "cloud.artifact.created", {"artifact_id": artifact.id, "type": "result"})
        service.checkpoint(job, 2, {"status": "result_persisted", "artifact_id": artifact.id})
        job.result_summary = response[:2000]
        job.current_step = "verified"
        service.event(job, "execution.completed", {"verified": True})
        queue.acknowledge(job)
        service.event(job, "cloud.job.completed", {"artifact_count": 1})
        db.commit()

    @staticmethod
    def _category(exc: Exception) -> str:
        text = str(exc).lower()
        for category in RETRYABLE:
            if category in text:
                return category
        return "invalid_request" if isinstance(exc, ValueError) else "unknown"

    @staticmethod
    def _safe_error(exc: Exception) -> str:
        category = CloudWorker._category(exc)
        return {
            "timeout": "Cloud execution timed out.", "rate_limit": "A provider rate limit delayed the job.",
            "network_error": "A temporary network error interrupted the job.",
            "provider_unavailable": "The AI provider is temporarily unavailable.",
            "worker_interruption": "The worker was interrupted.",
            "invalid_request": "The cloud task could not be executed safely.",
        }.get(category, "Cloud execution failed safely.")
