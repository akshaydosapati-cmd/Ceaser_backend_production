from __future__ import annotations

from sqlalchemy.orm import Session

from app.models.memory import Memory
from app.repositories.memory_repository import MemoryRepository


class MemoryService:
    def __init__(self, db: Session):
        self.memories = MemoryRepository(db)
        self.db = db

    def list(self, user_id: str | None = None) -> list[Memory]:
        return self.memories.list(user_id=user_id)

    def get(self, memory_id: str) -> Memory | None:
        return self.memories.get(memory_id)

    def create(self, user_id: str, memory_type: str, content: str, metadata: dict) -> Memory:
        memory = self.memories.create(user_id=user_id, memory_type=memory_type, content=content, metadata=metadata)
        self.db.commit()
        self.db.refresh(memory)
        return memory

    def search(self, query: str, user_id: str | None = None) -> list[Memory]:
        return self.memories.search(query=query, user_id=user_id)

    def delete(self, memory: Memory) -> None:
        self.memories.delete(memory)
        self.db.commit()
