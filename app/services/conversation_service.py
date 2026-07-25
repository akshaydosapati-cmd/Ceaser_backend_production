from __future__ import annotations

from sqlalchemy.orm import Session

from app.models.conversation import Conversation, Message
from app.intelligence.knowledge.repository import KnowledgeRepository
from app.repositories.conversation_repository import ConversationRepository


class ConversationService:
    def __init__(self, db: Session):
        self.conversations = ConversationRepository(db)
        self.db = db

    def list(self, user_id: str | None = None, limit: int = 50, offset: int = 0, archived: bool = False) -> list[Conversation]:
        return self.conversations.list(user_id=user_id, limit=limit, offset=offset, archived=archived)

    def get(self, conversation_id: str) -> Conversation | None:
        return self.conversations.get(conversation_id)

    def create(self, user_id: str, title: str | None = None) -> Conversation:
        title = title or "New Chat"
        conversation = self.conversations.create(user_id=user_id, title=title)
        self.db.commit()
        self.db.refresh(conversation)
        return conversation

    def rename(self, conversation: Conversation, title: str) -> Conversation:
        conversation = self.conversations.update_title(conversation=conversation, title=title)
        self.db.commit()
        self.db.refresh(conversation)
        return conversation

    def update(self, conversation: Conversation, title: str | None = None, pinned: bool | None = None, archived: bool | None = None) -> Conversation:
        conversation = self.conversations.update(conversation=conversation, title=title, pinned=pinned, archived=archived)
        self.db.commit()
        self.db.refresh(conversation)
        return conversation

    def delete(self, conversation: Conversation) -> None:
        self.conversations.delete(conversation)
        self.db.commit()

    def list_messages(self, conversation_id: str | None = None, limit: int = 100, offset: int = 0) -> list[Message]:
        return self.conversations.list_messages(conversation_id=conversation_id, limit=limit, offset=offset)

    def create_message(
        self,
        conversation_id: str,
        role: str,
        content: str,
        metadata: dict | None = None,
        *,
        ingest_knowledge: bool = True,
    ) -> Message:
        message = self.conversations.create_message(conversation_id=conversation_id, role=role, content=content, metadata=metadata)
        conversation = self.conversations.get(conversation_id)
        if ingest_knowledge and conversation and role in {"user", "assistant"}:
            try:
                KnowledgeRepository(self.db).ingest_text(
                    user_id=conversation.user_id,
                    title=f"{role.title()} message - {conversation.title}",
                    content=content,
                    source_type="conversation_message",
                    conversation_id=conversation_id,
                    metadata={"role": role, "message_id": message.id, **(metadata or {})},
                )
            except Exception:
                pass
        self.db.commit()
        self.db.refresh(message)
        return message

    def generate_title(self, message: str) -> str:
        stop_words = {"a", "an", "the", "for", "my", "me", "and", "or", "to", "in", "of"}
        words = [word.strip(".,!?").title() for word in message.split() if word.lower().strip(".,!?") not in stop_words]
        title = " ".join(words[:4]).strip()
        return title or "New Chat"
