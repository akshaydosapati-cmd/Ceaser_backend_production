from __future__ import annotations

from sqlalchemy.orm import Session

from app.models.project import Project
from app.repositories.project_repository import ProjectRepository


class ProjectService:
    def __init__(self, db: Session):
        self.projects = ProjectRepository(db)
        self.db = db

    def list(self, user_id: str | None = None) -> list[Project]:
        return self.projects.list(user_id=user_id)

    def get(self, project_id: str) -> Project | None:
        return self.projects.get(project_id)

    def create(self, user_id: str, name: str, description: str | None, status: str) -> Project:
        project = self.projects.create(user_id=user_id, name=name, description=description, status=status)
        self.db.commit()
        self.db.refresh(project)
        return project

    def update(self, project: Project, name: str | None = None, description: str | None = None, status: str | None = None) -> Project:
        if name is not None:
            project.name = name
        if description is not None:
            project.description = description
        if status is not None:
            project.status = status
        self.db.commit()
        self.db.refresh(project)
        return project

    def delete(self, project: Project) -> None:
        self.projects.delete(project)
        self.db.commit()
