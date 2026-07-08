from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.database.session import get_db
from app.core.security.access_control import require_agent_access
from app.core.security.dependencies import get_current_user
from app.models.user import User
from app.schemas.agent import AgentModulesUpdate, AgentRead, AgentUpdate
from app.services.agent_service import AgentService

router = APIRouter(prefix="/agents", tags=["agents"])


@router.get("", response_model=list[AgentRead])
def list_agents(user: Annotated[User, Depends(get_current_user)], db: Annotated[Session, Depends(get_db)]):
    return AgentService(db).list(user_id=user.id)


@router.get("/{agent_id}", response_model=AgentRead)
def get_agent(agent_id: str, user: Annotated[User, Depends(get_current_user)], db: Annotated[Session, Depends(get_db)]):
    return require_agent_access(db, user, agent_id)


@router.put("/{agent_id}", response_model=AgentRead)
def update_agent(agent_id: str, payload: AgentUpdate, user: Annotated[User, Depends(get_current_user)], db: Annotated[Session, Depends(get_db)]):
    service = AgentService(db)
    agent = require_agent_access(db, user, agent_id)
    if payload.enabled is not None:
        return service.set_enabled(agent, payload.enabled)
    return agent


@router.post("/{agent_id}/enable", response_model=AgentRead)
def enable_agent(agent_id: str, user: Annotated[User, Depends(get_current_user)], db: Annotated[Session, Depends(get_db)]):
    return AgentService(db).set_enabled(require_agent_access(db, user, agent_id), True)


@router.post("/{agent_id}/disable", response_model=AgentRead)
def disable_agent(agent_id: str, user: Annotated[User, Depends(get_current_user)], db: Annotated[Session, Depends(get_db)]):
    return AgentService(db).set_enabled(require_agent_access(db, user, agent_id), False)


@router.get("/{agent_id}/modules")
def list_modules(agent_id: str, user: Annotated[User, Depends(get_current_user)], db: Annotated[Session, Depends(get_db)]):
    return require_agent_access(db, user, agent_id).modules


@router.put("/{agent_id}/modules", response_model=AgentRead)
def update_modules(agent_id: str, payload: AgentModulesUpdate, user: Annotated[User, Depends(get_current_user)], db: Annotated[Session, Depends(get_db)]):
    agent = require_agent_access(db, user, agent_id)
    return AgentService(db).update_modules(agent, enabled_module_names=payload.module_names, enabled_module_ids=payload.moduleIds)
