from __future__ import annotations

from app.core.config.settings import settings
from app.models.voice import VoiceSettings
from app.services.voice.schemas import VoiceSettingsData


class VoiceSettingsService:
    def __init__(self, db):
        self.db = db

    def get_or_create(self, user_id: str) -> VoiceSettings:
        record = self.db.query(VoiceSettings).filter(VoiceSettings.user_id == user_id).first()
        if record:
            return record
        record = VoiceSettings(user_id=user_id, language=settings.voice_default_language)
        self.db.add(record)
        self.db.flush()
        return record

    def update(self, user_id: str, data: VoiceSettingsData | dict) -> VoiceSettings:
        record = self.get_or_create(user_id)
        values = data.model_dump() if isinstance(data, VoiceSettingsData) else data
        for field, value in values.items():
            if hasattr(record, field):
                setattr(record, field, value)
        self.db.flush()
        return record
