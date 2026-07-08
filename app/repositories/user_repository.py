from __future__ import annotations

from sqlalchemy.orm import Session

from app.models.user import User


class UserRepository:
    def __init__(self, db: Session):
        self.db = db

    def get(self, user_id: str) -> User | None:
        return self.db.get(User, user_id)

    def get_by_email(self, email: str) -> User | None:
        return self.db.query(User).filter(User.email == email).first()

    def create(self, email: str, user_id: str | None = None) -> User:
        user = User(email=email)
        if user_id:
            user.id = user_id
        self.db.add(user)
        self.db.flush()
        return user

    def get_or_create(self, email: str, user_id: str | None = None) -> User:
        user = self.get_by_email(email)
        if user:
            return user
        return self.create(email=email, user_id=user_id)
