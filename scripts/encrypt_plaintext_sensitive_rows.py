from __future__ import annotations

from app.core.database.session import SessionLocal
from app.models.conversation import Message
from app.models.memory import Memory


def encrypt_model_rows(rows) -> int:
    updated = 0
    for row in rows:
        if not getattr(row, "content_encrypted", None):
            row.content = row.raw_content
            updated += 1
        if not getattr(row, "metadata_encrypted", None):
            row.extra_metadata = row.raw_metadata or {}
            updated += 1
    return updated


def main() -> None:
    db = SessionLocal()
    try:
        updated = 0
        updated += encrypt_model_rows(db.query(Message).all())
        updated += encrypt_model_rows(db.query(Memory).all())
        db.commit()
        print(f"Encrypted {updated} plaintext sensitive fields.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
