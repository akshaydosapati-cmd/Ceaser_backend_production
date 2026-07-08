from __future__ import annotations

from app.models.mixins import utc_now
from app.models.voice import VoiceSession


class VoiceSessionManager:
    def __init__(self, db):
        self.db = db

    def start(self, *, user_id: str, conversation_id: str | None = None) -> VoiceSession:
        session = VoiceSession(user_id=user_id, conversation_id=conversation_id, status="listening", started_at=utc_now())
        self.db.add(session)
        self.db.flush()
        return session

    def get(self, session_id: str) -> VoiceSession | None:
        return self.db.get(VoiceSession, session_id)

    def set_status(self, session: VoiceSession, status: str, error_message: str | None = None) -> VoiceSession:
        session.status = status
        session.error_message = error_message
        if status in {"completed", "error"}:
            session.ended_at = utc_now()
        self.db.flush()
        return session
