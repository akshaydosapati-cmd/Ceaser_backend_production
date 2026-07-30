from __future__ import annotations

from sqlalchemy.orm import Session

from app.models.conversation import Conversation, Message


class ConversationRepository:
    def __init__(self, db: Session):
        self.db = db

    def list(self, user_id: str | None = None, limit: int = 50, offset: int = 0, archived: bool = False) -> list[Conversation]:
        query = self.db.query(Conversation)
        if user_id:
            query = query.filter(Conversation.user_id == user_id)
        query = query.filter(Conversation.archived.is_(archived))
        return query.order_by(Conversation.pinned.desc(), Conversation.created_at.desc()).offset(offset).limit(limit).all()

    def get(self, conversation_id: str) -> Conversation | None:
        return self.db.get(Conversation, conversation_id)

    def create(self, user_id: str, title: str) -> Conversation:
        conversation = Conversation(user_id=user_id, title=title)
        self.db.add(conversation)
        self.db.flush()
        return conversation

    def update_title(self, conversation: Conversation, title: str) -> Conversation:
        conversation.title = title
        self.db.flush()
        return conversation

    def update(self, conversation: Conversation, title: str | None = None, pinned: bool | None = None, archived: bool | None = None) -> Conversation:
        if title is not None:
            conversation.title = title
        if pinned is not None:
            conversation.pinned = pinned
        if archived is not None:
            conversation.archived = archived
        self.db.flush()
        return conversation

    def delete(self, conversation: Conversation) -> None:
        self.db.delete(conversation)
        self.db.flush()

    def list_messages(self, conversation_id: str | None = None, limit: int | None = 100, offset: int = 0) -> list[Message]:
        query = self.db.query(Message)
        if conversation_id:
            query = query.filter(Message.conversation_id == conversation_id)
        query = query.order_by(Message.created_at.asc()).offset(offset)
        if limit is not None:
            query = query.limit(limit)
        return query.all()

    def list_recent_messages(self, conversation_id: str, limit: int = 24) -> list[Message]:
        """Return the latest messages in chronological order without loading a full chat."""
        messages = (
            self.db.query(Message)
            .filter(Message.conversation_id == conversation_id)
            .order_by(Message.created_at.desc())
            .limit(limit)
            .all()
        )
        return list(reversed(messages))

    def create_message(self, conversation_id: str, role: str, content: str, metadata: dict | None = None) -> Message:
        message = Message(conversation_id=conversation_id, role=role, content=content, extra_metadata=metadata or {})
        self.db.add(message)
        self.db.flush()
        return message
