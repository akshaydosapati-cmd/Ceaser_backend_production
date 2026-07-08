from sqlalchemy import ForeignKey, String, Boolean
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database.base import Base
from app.models.mixins import UUIDPrimaryKeyMixin


class Agent(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "agents"

    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(80), nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    modules: Mapped[list["AgentModule"]] = relationship(back_populates="agent", cascade="all, delete-orphan")


class AgentModule(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "agent_modules"

    agent_id: Mapped[str] = mapped_column(ForeignKey("agents.id", ondelete="CASCADE"), index=True, nullable=False)
    module_name: Mapped[str] = mapped_column(String(120), nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    agent: Mapped["Agent"] = relationship(back_populates="modules")
