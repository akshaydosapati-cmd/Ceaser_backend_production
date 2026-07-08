from __future__ import annotations

from app.core.database.session import SessionLocal
from app.models.conversation import Message
from app.models.memory import Memory
from app.services.orchestrator.memory_capture import MemoryCapture


def dedupe_memories(db) -> int:
    memories = db.query(Memory).order_by(Memory.created_at.asc()).all()
    seen: set[tuple[str, str, str]] = set()
    deleted = 0
    for memory in memories:
        key = (memory.workspace_id, memory.memory_type, memory.content.lower())
        if key in seen:
            db.delete(memory)
            deleted += 1
            continue
        seen.add(key)
    if deleted:
        db.commit()
    return deleted


def main() -> None:
    db = SessionLocal()
    try:
        capture = MemoryCapture(db)
        created = 0
        messages = db.query(Message).filter(Message.role == "user").order_by(Message.created_at.asc()).all()
        for message in messages:
            if not message.conversation:
                continue
            created += len(capture.capture(workspace_id=message.conversation.workspace_id, message=message.content))
        deleted = dedupe_memories(db)
        print(f"Backfilled {created} memories from saved chats. Removed {deleted} duplicate memories.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
