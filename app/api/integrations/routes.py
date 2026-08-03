from typing import Annotated
import hashlib
import hmac
import logging

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.core.config.settings import settings
from app.core.database.session import get_db
from app.models.integration import Integration
from app.core.security.dependencies import get_current_user
from app.models.user import User
from app.schemas.integration import IntegrationConnectRequest, IntegrationConnectResponse, IntegrationMetadataRead, IntegrationProviderRead, IntegrationRead, IntegrationRecordRead, IntegrationStatusRead
from app.services.integrations import IntegrationManager

router = APIRouter(prefix="/integrations", tags=["integrations"])
logger = logging.getLogger(__name__)


def manager(db: Session) -> IntegrationManager:
    return IntegrationManager(db)


@router.get("", response_model=list[IntegrationRead])
def list_integrations(user: Annotated[User, Depends(get_current_user)], db: Annotated[Session, Depends(get_db)]):
    return manager(db).list(user.id)


@router.get("/providers", response_model=list[IntegrationProviderRead])
def list_providers(user: Annotated[User, Depends(get_current_user)], db: Annotated[Session, Depends(get_db)]):
    _ = user
    return manager(db).providers()


@router.get("/{provider}/status", response_model=IntegrationStatusRead)
def provider_status(provider: str, user: Annotated[User, Depends(get_current_user)], db: Annotated[Session, Depends(get_db)]):
    try:
        return manager(db).status(user.id, provider)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/{provider}/connect", response_model=IntegrationConnectResponse)
def connect_provider(provider: str, payload: IntegrationConnectRequest, user: Annotated[User, Depends(get_current_user)], db: Annotated[Session, Depends(get_db)]):
    try:
        if payload.code:
            integration = manager(db).complete_connect(user.id, provider, payload.code, payload.workspace_id)
            return {"provider": provider, "integration": manager(db)._read(provider, integration)}
        return manager(db).start_connect(user.id, provider, payload.workspace_id, payload.return_url)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/{provider}/callback")
def oauth_callback(provider: str, code: str, db: Annotated[Session, Depends(get_db)], state: str | None = None):
    frontend_url = settings.frontend_app_url.rstrip("/")
    if not state:
        return RedirectResponse(f"{frontend_url}/?view=integrations&integration={provider}&status=failed&reason=missing_state")
    try:
        integration = manager(db).complete_connect_by_state(provider, code, state)
        frontend_url = (integration.metadata_json or {}).get("return_url") or frontend_url
        frontend_url = str(frontend_url).rstrip("/")
    except ValueError:
        return RedirectResponse(f"{frontend_url}/?view=integrations&integration={provider}&status=failed&reason=expired")
    except Exception:
        return RedirectResponse(f"{frontend_url}/?view=integrations&integration={provider}&status=failed&reason=provider")
    return RedirectResponse(f"{frontend_url}/?view=integrations&integration={provider}&status=connected")


@router.post("/{provider}/disconnect", response_model=IntegrationRecordRead)
def disconnect_provider(provider: str, user: Annotated[User, Depends(get_current_user)], db: Annotated[Session, Depends(get_db)]):
    try:
        return manager(db).disconnect(user.id, provider)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/{provider}/refresh", response_model=IntegrationRecordRead)
def refresh_provider(provider: str, user: Annotated[User, Depends(get_current_user)], db: Annotated[Session, Depends(get_db)]):
    try:
        return manager(db).refresh(user.id, provider)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/{provider}/sync", response_model=IntegrationRecordRead)
def sync_provider(provider: str, user: Annotated[User, Depends(get_current_user)], db: Annotated[Session, Depends(get_db)]):
    try:
        return manager(db).sync(user.id, provider)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/{provider}/metadata", response_model=IntegrationMetadataRead)
def provider_metadata(provider: str, user: Annotated[User, Depends(get_current_user)], db: Annotated[Session, Depends(get_db)]):
    try:
        return manager(db).metadata(user.id, provider)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/notion/webhook")
async def notion_webhook(
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    x_notion_signature: str | None = Header(default=None, alias="X-Notion-Signature"),
):
    raw_body = await request.body()
    try:
        payload = await request.json()
    except Exception as exc:
        raise HTTPException(status_code=400, detail="Invalid webhook payload.") from exc

    verification_token = payload.get("verification_token") if isinstance(payload, dict) else None
    if verification_token:
        logger.info("Notion webhook verification token received")
        return {"received": True, "verification_token": verification_token}

    configured_token = settings.notion_webhook_verification_token
    if configured_token and x_notion_signature:
        expected = "sha256=" + hmac.new(configured_token.encode(), raw_body, hashlib.sha256).hexdigest()
        if not hmac.compare_digest(expected, x_notion_signature):
            raise HTTPException(status_code=401, detail="Invalid Notion webhook signature.")
    elif configured_token:
        raise HTTPException(status_code=401, detail="Missing Notion webhook signature.")

    workspace_id = payload.get("workspace_id") if isinstance(payload, dict) else None
    event_type = payload.get("type") if isinstance(payload, dict) else None
    entity = payload.get("entity") if isinstance(payload, dict) else {}
    query = db.query(Integration).filter(Integration.provider == "notion", Integration.status == "connected")
    integrations = query.all()
    touched = 0
    for integration in integrations:
        metadata = integration.metadata_json or {}
        if workspace_id and metadata.get("workspace_id") and metadata.get("workspace_id") != workspace_id:
            continue
        integration.metadata_json = {
            **metadata,
            "notion_webhook_stale": True,
            "notion_webhook_last_event": {
                "type": event_type,
                "workspace_id": workspace_id,
                "entity": entity if isinstance(entity, dict) else {},
            },
        }
        touched += 1
    db.commit()
    logger.info("Notion webhook processed event_type=%s stale_integrations=%s", event_type, touched)
    return {"received": True, "stale_integrations": touched}
