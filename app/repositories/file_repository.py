from __future__ import annotations

from sqlalchemy.orm import Session

from app.models.file import File


class FileRepository:
    def __init__(self, db: Session):
        self.db = db

    def list(self, user_id: str | None = None) -> list[File]:
        query = self.db.query(File)
        if user_id:
            query = query.filter(File.user_id == user_id)
        return query.order_by(File.created_at.desc()).all()

    def create(self, user_id: str, project_id: str | None, name: str, file_type: str, storage_path: str) -> File:
        file = File(user_id=user_id, project_id=project_id, name=name, file_type=file_type, storage_path=storage_path)
        self.db.add(file)
        self.db.flush()
        return file

    def get(self, file_id: str) -> File | None:
        return self.db.get(File, file_id)

    def update_project(self, file: File, project_id: str | None) -> File:
        file.project_id = project_id
        self.db.flush()
        return file

    def delete(self, file: File) -> None:
        self.db.delete(file)
        self.db.flush()
