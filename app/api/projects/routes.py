from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.database.session import get_db
from app.core.security.access_control import require_project_access
from app.core.security.dependencies import get_current_user
from app.models.user import User
from app.schemas.project import ProjectCreate, ProjectMemberCreate, ProjectMemberRead, ProjectMemberUpdate, ProjectRead, ProjectUpdate
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


@router.get("/{project_id}/members", response_model=list[ProjectMemberRead])
def list_project_members(project_id: str, user: Annotated[User, Depends(get_current_user)], db: Annotated[Session, Depends(get_db)]):
    project = require_project_access(db, user, project_id)
    return ProjectService(db).list_members(project)


@router.post("/{project_id}/members", response_model=ProjectMemberRead, status_code=status.HTTP_201_CREATED)
def add_project_member(project_id: str, payload: ProjectMemberCreate, user: Annotated[User, Depends(get_current_user)], db: Annotated[Session, Depends(get_db)]):
    project = require_project_access(db, user, project_id)
    return ProjectService(db).add_member(project, email=payload.email, name=payload.name, role=payload.role, status=payload.status)


@router.patch("/{project_id}/members/{member_id}", response_model=ProjectMemberRead)
def update_project_member(project_id: str, member_id: str, payload: ProjectMemberUpdate, user: Annotated[User, Depends(get_current_user)], db: Annotated[Session, Depends(get_db)]):
    project = require_project_access(db, user, project_id)
    service = ProjectService(db)
    member = service.get_member(project, member_id)
    if not member:
        raise HTTPException(status_code=404, detail="Project member not found")
    return service.update_member(member, name=payload.name, role=payload.role, status=payload.status)


@router.delete("/{project_id}/members/{member_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_project_member(project_id: str, member_id: str, user: Annotated[User, Depends(get_current_user)], db: Annotated[Session, Depends(get_db)]):
    project = require_project_access(db, user, project_id)
    service = ProjectService(db)
    member = service.get_member(project, member_id)
    if not member:
        raise HTTPException(status_code=404, detail="Project member not found")
    if member.role == "owner":
        raise HTTPException(status_code=400, detail="Project owner cannot be removed")
    service.remove_member(member)
    return None
