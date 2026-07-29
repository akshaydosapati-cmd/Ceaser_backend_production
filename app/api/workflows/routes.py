from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.database.session import get_db
from app.core.security.dependencies import get_current_user
from app.models.user import User
from app.schemas.workflow import WorkflowRunRead, WorkflowStartRequest, WorkflowStartResponse, WorkflowStepRead, WorkflowTemplateRead
from app.services.workflows import WorkflowOrchestrator
from app.services.workflows.workflow_manager import WorkflowManager

router = APIRouter(prefix="/workflows", tags=["workflows"])


@router.get("/templates", response_model=list[WorkflowTemplateRead])
def workflow_templates(user: Annotated[User, Depends(get_current_user)], db: Annotated[Session, Depends(get_db)]):
    _ = user
    return WorkflowManager(db).templates_list()


@router.post("/start", response_model=WorkflowStartResponse)
def start_workflow(payload: WorkflowStartRequest, user: Annotated[User, Depends(get_current_user)], db: Annotated[Session, Depends(get_db)]):
    return WorkflowOrchestrator(db).run(user_id=user.id, message=payload.message, conversation_id=payload.conversation_id, file_ids=payload.file_ids).model_dump()


@router.get("", response_model=list[WorkflowRunRead])
def list_workflows(user: Annotated[User, Depends(get_current_user)], db: Annotated[Session, Depends(get_db)]):
    return WorkflowManager(db).list(user_id=user.id)


@router.get("/{workflow_id}", response_model=WorkflowRunRead)
def get_workflow(workflow_id: str, user: Annotated[User, Depends(get_current_user)], db: Annotated[Session, Depends(get_db)]):
    run = WorkflowManager(db).get(workflow_id=workflow_id, user_id=user.id)
    if not run:
        raise HTTPException(status_code=404, detail="Workflow not found")
    return run


@router.get("/{workflow_id}/steps", response_model=list[WorkflowStepRead])
def get_workflow_steps(workflow_id: str, user: Annotated[User, Depends(get_current_user)], db: Annotated[Session, Depends(get_db)]):
    manager = WorkflowManager(db)
    run = manager.get(workflow_id=workflow_id, user_id=user.id)
    if not run:
        raise HTTPException(status_code=404, detail="Workflow not found")
    return manager.steps(run)


@router.post("/{workflow_id}/cancel", response_model=WorkflowRunRead)
def cancel_workflow(workflow_id: str, user: Annotated[User, Depends(get_current_user)], db: Annotated[Session, Depends(get_db)]):
    manager = WorkflowManager(db)
    run = manager.get(workflow_id=workflow_id, user_id=user.id)
    if not run:
        raise HTTPException(status_code=404, detail="Workflow not found")
    return manager.cancel(run)


@router.post("/{workflow_id}/status/{action}", response_model=WorkflowRunRead)
def transition_workflow(workflow_id: str, action: str, user: Annotated[User, Depends(get_current_user)], db: Annotated[Session, Depends(get_db)]):
    manager = WorkflowManager(db)
    run = manager.get(workflow_id=workflow_id, user_id=user.id)
    if not run:
        raise HTTPException(status_code=404, detail="Workflow not found")
    if action not in {"approved", "archived"}:
        raise HTTPException(status_code=400, detail="Unsupported workflow action")
    return manager.transition(run, action)


@router.post("/{workflow_id}/regenerate", response_model=WorkflowStartResponse)
def regenerate_workflow(workflow_id: str, user: Annotated[User, Depends(get_current_user)], db: Annotated[Session, Depends(get_db)]):
    run = WorkflowManager(db).get(workflow_id=workflow_id, user_id=user.id)
    if not run:
        raise HTTPException(status_code=404, detail="Workflow not found")
    metadata = run.metadata_json or {}
    message = metadata.get("message")
    if not isinstance(message, str) or not message.strip():
        raise HTTPException(status_code=400, detail="This older workflow cannot be regenerated because its original brief is unavailable.")
    return WorkflowOrchestrator(db).run(user_id=user.id, message=message, conversation_id=metadata.get("conversation_id"), file_ids=metadata.get("file_ids") or []).model_dump()


@router.delete("/{workflow_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_workflow(workflow_id: str, user: Annotated[User, Depends(get_current_user)], db: Annotated[Session, Depends(get_db)]):
    manager = WorkflowManager(db)
    run = manager.get(workflow_id=workflow_id, user_id=user.id)
    if not run:
        raise HTTPException(status_code=404, detail="Workflow not found")
    manager.delete(run)
