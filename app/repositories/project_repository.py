from __future__ import annotations

from sqlalchemy.orm import Session

from app.models.project import Project


class ProjectRepository:
    def __init__(self, db: Session):
        self.db = db

    def list(self, user_id: str | None = None) -> list[Project]:
        query = self.db.query(Project)
        if user_id:
            query = query.filter(Project.user_id == user_id)
        return query.order_by(Project.created_at.desc()).all()

    def get(self, project_id: str) -> Project | None:
        return self.db.get(Project, project_id)

    def create(self, user_id: str, name: str, description: str | None, status: str) -> Project:
        project = Project(user_id=user_id, name=name, description=description, status=status)
        self.db.add(project)
        self.db.flush()
        return project

    def delete(self, project: Project) -> None:
        self.db.delete(project)
        self.db.flush()
