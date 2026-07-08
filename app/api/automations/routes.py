from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.database.session import get_db
from app.core.security.dependencies import get_current_user
from app.models.user import User
from app.schemas.automation import AutomationCreate, AutomationRead, AutomationRunRead, AutomationTemplateRead, AutomationUpdate
from app.services.automations import AutomationManager
from app.services.automations.automation_scheduler import AutomationScheduler
from app.services.automations.automation_worker import automation_worker

router = APIRouter(prefix="/automations", tags=["automations"])


@router.get("/templates", response_model=list[AutomationTemplateRead])
def list_templates(user: Annotated[User, Depends(get_current_user)], db: Annotated[Session, Depends(get_db)]):
    _ = user
    return AutomationManager(db).template_list()


@router.get("/worker/health")
def automation_worker_health(user: Annotated[User, Depends(get_current_user)]):
    _ = user
    return automation_worker.state.as_dict()


@router.post("/worker/run-due", response_model=list[AutomationRunRead])
def run_due_automations(user: Annotated[User, Depends(get_current_user)], db: Annotated[Session, Depends(get_db)]):
    return AutomationScheduler(db).run_due(user_id=user.id)


@router.get("", response_model=list[AutomationRead])
def list_automations(user: Annotated[User, Depends(get_current_user)], db: Annotated[Session, Depends(get_db)]):
    return AutomationManager(db).list(user_id=user.id)


@router.post("", response_model=AutomationRead, status_code=status.HTTP_201_CREATED)
def create_automation(payload: AutomationCreate, user: Annotated[User, Depends(get_current_user)], db: Annotated[Session, Depends(get_db)]):
    return AutomationManager(db).create(user_id=user.id, **payload.model_dump())


@router.get("/{automation_id}", response_model=AutomationRead)
def get_automation(automation_id: str, user: Annotated[User, Depends(get_current_user)], db: Annotated[Session, Depends(get_db)]):
    automation = AutomationManager(db).get(automation_id=automation_id, user_id=user.id)
    if not automation:
        raise HTTPException(status_code=404, detail="Automation not found")
    return automation


@router.put("/{automation_id}", response_model=AutomationRead)
def update_automation(automation_id: str, payload: AutomationUpdate, user: Annotated[User, Depends(get_current_user)], db: Annotated[Session, Depends(get_db)]):
    manager = AutomationManager(db)
    automation = manager.get(automation_id=automation_id, user_id=user.id)
    if not automation:
        raise HTTPException(status_code=404, detail="Automation not found")
    return manager.update(automation, **payload.model_dump(exclude_unset=True))


@router.delete("/{automation_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_automation(automation_id: str, user: Annotated[User, Depends(get_current_user)], db: Annotated[Session, Depends(get_db)]):
    manager = AutomationManager(db)
    automation = manager.get(automation_id=automation_id, user_id=user.id)
    if not automation:
        raise HTTPException(status_code=404, detail="Automation not found")
    manager.delete(automation)
    return None


@router.post("/{automation_id}/pause", response_model=AutomationRead)
def pause_automation(automation_id: str, user: Annotated[User, Depends(get_current_user)], db: Annotated[Session, Depends(get_db)]):
    manager = AutomationManager(db)
    automation = manager.get(automation_id=automation_id, user_id=user.id)
    if not automation:
        raise HTTPException(status_code=404, detail="Automation not found")
    return manager.pause(automation)


@router.post("/{automation_id}/resume", response_model=AutomationRead)
def resume_automation(automation_id: str, user: Annotated[User, Depends(get_current_user)], db: Annotated[Session, Depends(get_db)]):
    manager = AutomationManager(db)
    automation = manager.get(automation_id=automation_id, user_id=user.id)
    if not automation:
        raise HTTPException(status_code=404, detail="Automation not found")
    return manager.resume(automation)


@router.post("/{automation_id}/run-now", response_model=AutomationRunRead)
def run_automation_now(automation_id: str, user: Annotated[User, Depends(get_current_user)], db: Annotated[Session, Depends(get_db)]):
    manager = AutomationManager(db)
    automation = manager.get(automation_id=automation_id, user_id=user.id)
    if not automation:
        raise HTTPException(status_code=404, detail="Automation not found")
    return manager.run_now(automation)


@router.get("/{automation_id}/runs", response_model=list[AutomationRunRead])
def list_automation_runs(automation_id: str, user: Annotated[User, Depends(get_current_user)], db: Annotated[Session, Depends(get_db)]):
    manager = AutomationManager(db)
    automation = manager.get(automation_id=automation_id, user_id=user.id)
    if not automation:
        raise HTTPException(status_code=404, detail="Automation not found")
    return manager.runs(automation)
