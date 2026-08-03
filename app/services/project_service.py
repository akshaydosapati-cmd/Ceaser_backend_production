from __future__ import annotations

from sqlalchemy.orm import Session

from app.models.project import Project, ProjectMember
from app.repositories.project_repository import ProjectRepository
from app.repositories.user_repository import UserRepository


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
        self._ensure_owner_member(project)
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

    def list_members(self, project: Project) -> list[ProjectMember]:
        self._ensure_owner_member(project)
        self.db.commit()
        return (
            self.db.query(ProjectMember)
            .filter(ProjectMember.project_id == project.id, ProjectMember.status != "removed")
            .order_by(ProjectMember.created_at.asc())
            .all()
        )

    def add_member(self, project: Project, *, email: str, name: str | None = None, role: str = "viewer", status: str = "invited") -> ProjectMember:
        normalized_email = email.strip().lower()
        user = UserRepository(self.db).get_by_email(normalized_email)
        member = (
            self.db.query(ProjectMember)
            .filter(ProjectMember.project_id == project.id, ProjectMember.email == normalized_email)
            .first()
        )
        if member:
            member.name = name or member.name
            member.role = role
            member.status = status
            member.user_id = user.id if user else member.user_id
        else:
            member = ProjectMember(
                project_id=project.id,
                user_id=user.id if user else None,
                email=normalized_email,
                name=name,
                role=role,
                status=status,
            )
            self.db.add(member)
        self.db.commit()
        self.db.refresh(member)
        return member

    def update_member(self, member: ProjectMember, *, name: str | None = None, role: str | None = None, status: str | None = None) -> ProjectMember:
        if name is not None:
            member.name = name
        if role is not None:
            member.role = role
        if status is not None:
            member.status = status
        self.db.commit()
        self.db.refresh(member)
        return member

    def remove_member(self, member: ProjectMember) -> None:
        member.status = "removed"
        self.db.commit()

    def get_member(self, project: Project, member_id: str) -> ProjectMember | None:
        return (
            self.db.query(ProjectMember)
            .filter(ProjectMember.project_id == project.id, ProjectMember.id == member_id)
            .first()
        )

    def _ensure_owner_member(self, project: Project) -> ProjectMember | None:
        owner = UserRepository(self.db).get(project.user_id)
        if not owner:
            return None
        existing = (
            self.db.query(ProjectMember)
            .filter(ProjectMember.project_id == project.id, ProjectMember.email == owner.email.lower())
            .first()
        )
        if existing:
            existing.role = "owner"
            existing.status = "active"
            existing.user_id = owner.id
            return existing
        member = ProjectMember(
            project_id=project.id,
            user_id=owner.id,
            email=owner.email.lower(),
            name=owner.email.split("@", 1)[0],
            role="owner",
            status="active",
        )
        self.db.add(member)
        self.db.flush()
        return member
