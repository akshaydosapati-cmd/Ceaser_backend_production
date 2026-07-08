from typing import Annotated

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.core.database.session import get_db
from app.core.security.access_control import require_project_access
from app.core.security.dependencies import get_current_user
from app.models.user import User
from app.schemas.project import ProjectCreate, ProjectRead, ProjectUpdate
from app.services.project_service import ProjectService

router = APIRouter(prefix="/projects", tags=["projects"])


@router.get("", response_model=list[ProjectRead])
def list_projects(user: Annotated[User, Depends(get_current_user)], db: Annotated[Session, Depends(get_db)]):
    return ProjectService(db).list(user_id=user.id)


@router.post("", response_model=ProjectRead, status_code=status.HTTP_201_CREATED)
def create_project(payload: ProjectCreate, user: Annotated[User, Depends(get_current_user)], db: Annotated[Session, Depends(get_db)]):
    return ProjectService(db).create(user_id=user.id, name=payload.name, description=payload.description, status=payload.status)


@router.get("/{project_id}", response_model=ProjectRead)
def get_project(project_id: str, user: Annotated[User, Depends(get_current_user)], db: Annotated[Session, Depends(get_db)]):
    return require_project_access(db, user, project_id)


@router.patch("/{project_id}", response_model=ProjectRead)
def update_project(project_id: str, payload: ProjectUpdate, user: Annotated[User, Depends(get_current_user)], db: Annotated[Session, Depends(get_db)]):
    project = require_project_access(db, user, project_id)
    return ProjectService(db).update(project, name=payload.name, description=payload.description, status=payload.status)


@router.delete("/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_project(project_id: str, user: Annotated[User, Depends(get_current_user)], db: Annotated[Session, Depends(get_db)]):
    ProjectService(db).delete(require_project_access(db, user, project_id))
    return None
