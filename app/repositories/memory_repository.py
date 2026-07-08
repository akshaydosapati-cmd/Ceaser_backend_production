from __future__ import annotations

from sqlalchemy.orm import Session

from app.models.memory import Memory


class MemoryRepository:
    def __init__(self, db: Session):
        self.db = db

    def list(self, user_id: str | None = None) -> list[Memory]:
        query = self.db.query(Memory)
        if user_id:
            query = query.filter(Memory.user_id == user_id)
        return query.order_by(Memory.created_at.desc()).all()

    def get(self, memory_id: str) -> Memory | None:
        return self.db.get(Memory, memory_id)

    def create(self, user_id: str, memory_type: str, content: str, metadata: dict) -> Memory:
        memory = Memory(user_id=user_id, memory_type=memory_type, content=content, extra_metadata=metadata)
        self.db.add(memory)
        self.db.flush()
        return memory

    def delete(self, memory: Memory) -> None:
        self.db.delete(memory)
        self.db.flush()

    def find_exact(self, user_id: str, memory_type: str, content: str) -> Memory | None:
        for memory in self.list(user_id=user_id):
            if memory.memory_type == memory_type and memory.content == content:
                return memory
        return None

    def search(self, query: str, user_id: str | None = None) -> list[Memory]:
        db_query = self.db.query(Memory)
        if user_id:
            db_query = db_query.filter(Memory.user_id == user_id)
        memories = db_query.order_by(Memory.created_at.desc()).all()
        if not query:
            return memories
        normalized_query = query.lower()
        return [memory for memory in memories if normalized_query in memory.content.lower()]
