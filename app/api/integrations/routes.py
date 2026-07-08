from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.core.config.settings import settings
from app.core.database.session import get_db
from app.core.security.dependencies import get_current_user
from app.models.user import User
from app.schemas.integration import IntegrationConnectRequest, IntegrationConnectResponse, IntegrationMetadataRead, IntegrationProviderRead, IntegrationRead, IntegrationRecordRead, IntegrationStatusRead
from app.services.integrations import IntegrationManager

router = APIRouter(prefix="/integrations", tags=["integrations"])


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
        return manager(db).start_connect(user.id, provider, payload.workspace_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/{provider}/callback")
def oauth_callback(provider: str, code: str, db: Annotated[Session, Depends(get_db)], state: str | None = None):
    frontend_url = settings.google_redirect_base_url.replace(":8000", ":3000")
    if not state:
        return RedirectResponse(f"{frontend_url}/?view=integrations&integration={provider}&status=failed&reason=missing_state")
    try:
        manager(db).complete_connect_by_state(provider, code, state)
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
