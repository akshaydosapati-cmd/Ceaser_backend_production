from datetime import datetime
from sqlalchemy import DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column
from app.core.database.base import Base
from app.core.security.encryption import decrypt_json, encrypt_json
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin

class SocialPublishTask(UUIDPrimaryKeyMixin,TimestampMixin,Base):
    __tablename__="social_publish_tasks"
    user_id:Mapped[str]=mapped_column(ForeignKey("users.id",ondelete="CASCADE"),index=True,nullable=False)
    task_id:Mapped[str]=mapped_column(String(120),index=True,unique=True,nullable=False)
    device_id:Mapped[str]=mapped_column(String(120),index=True,nullable=False)
    platform:Mapped[str]=mapped_column(String(80),nullable=False)
    status:Mapped[str]=mapped_column(String(40),index=True,nullable=False,default="WAITING_FOR_CONFIRMATION")
    draft_encrypted:Mapped[str]=mapped_column(Text,nullable=False)
    browser_session_id:Mapped[str|None]=mapped_column(String(120),nullable=True)
    expires_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),index=True,nullable=False)
    published_request_id:Mapped[str|None]=mapped_column(String(120),nullable=True)
    @property
    def draft(self):return decrypt_json(self.draft_encrypted)
    @draft.setter
    def draft(self,value):self.draft_encrypted=encrypt_json(value or {})
