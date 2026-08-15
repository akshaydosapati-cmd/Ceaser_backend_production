from __future__ import annotations

from uuid import uuid4

from sqlalchemy.orm import Session

from app.agents.v2 import DeviceCapabilityRequest
from app.models.user import User
from app.services.audit_service import AuditService
from app.services.device_gateway_service import DeviceGatewayService


SAFE_CAPABILITIES = {
    "browser.start", "browser.navigate", "browser.current_page", "browser.inspect", "browser.find", "browser.click",
    "browser.type", "browser.select", "browser.check", "browser.uncheck", "browser.scroll", "browser.hover", "browser.wait",
    "browser.upload", "browser.download", "browser.back", "browser.forward", "browser.reload", "browser.tabs", "browser.open_tab",
    "browser.close_tab", "browser.screenshot", "browser.extract", "browser.verify", "browser.cancel",
}
PROTECTED_ACTIONS = {"publish", "post", "send", "submit", "purchase", "checkout", "delete", "subscribe", "account_change", "security_change"}


class BrowserAutomationService:
    """Validates and dispatches structured browser actions through the existing Device Gateway."""

    def __init__(self, db: Session):
        self.db = db
        self.gateway = DeviceGatewayService(db)

    def dispatch(self, user: User, *, capability: str, arguments: dict, task_id: str | None = None, device_id: str | None = None, confirmed: bool = False):
        if capability not in SAFE_CAPABILITIES:
            return {"status": "failed", "error": "unsafe_action"}
        action_type = str(arguments.get("action_type") or "").lower()
        protected = action_type in PROTECTED_ACTIONS or bool(arguments.get("external_write")) or capability == "browser.upload"
        if protected and not confirmed:
            self._event(user.id, "browser.waiting_for_confirmation", task_id, device_id, {"action": action_type or capability})
            return {"status": "confirmation_required", "error": "confirmation_required"}
        available = [item for item in self.gateway.availability(user.id, capability, preferred_device_id=device_id) if item.connected and item.authenticated and item.authorized]
        if not available:
            return {"status": "waiting_for_device", "error": "device_disconnected"}
        if len(available) > 1 and not any(item.preferred for item in available):
            return {"status": "failed", "error": "ambiguous_device"}
        selected = next((item for item in available if item.preferred), available[0])
        task_id = task_id or f"browser_{uuid4().hex}"
        request = DeviceCapabilityRequest(
            request_id=f"browser_{uuid4().hex}", task_id=task_id, agent_id="friday", device_id=selected.device_id,
            capability=capability, arguments=arguments, confirmation_requirement="already_confirmed" if protected else "none",
            timeout_seconds=300, authorization={"user_id": user.id}, metadata={"workload": "browser_automation", "browser_goal": str(arguments.get("goal") or "")[:1000], "browser_step": int(arguments.get("step") or 1)},
        )
        command = self.gateway.submit(user, request)
        return {"status": "queued", "request_id": command.request_id, "task_id": task_id, "device_id": selected.device_id}

    def _event(self, user_id, action, task_id, device_id, metadata):
        AuditService(self.db).record(user_id=user_id, action=action, resource_type="browser_task", resource_id=task_id, metadata={"task_id": task_id, "device_id": device_id, **metadata})
