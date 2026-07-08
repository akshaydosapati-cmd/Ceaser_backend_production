from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.api.auth.routes import get_current_user
from app.models.user import User
from app.services.capabilities import capability_registry

router = APIRouter(prefix="/capabilities", tags=["capabilities"])


@router.get("")
def list_capabilities(
    user: Annotated[User, Depends(get_current_user)],
    agent: str | None = Query(default=None),
    surface: str | None = Query(default=None),
) -> dict:
    capabilities = capability_registry.list()
    if agent:
        capabilities = capability_registry.by_agent(agent)
    if surface:
        capabilities = [capability for capability in capabilities if bool(getattr(capability.surfaces, surface, False))]
    return {"capabilities": [capability.as_dict() for capability in capabilities]}
