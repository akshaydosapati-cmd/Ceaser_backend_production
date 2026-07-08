from __future__ import annotations

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models.agent import Agent
from app.models.conversation import Conversation
from app.models.file import File
from app.models.memory import Memory
from app.models.project import Project
from app.models.user import User


def require_user_scope(user: User, resource_user_id: str | None) -> None:
    if resource_user_id is not None and resource_user_id != user.id:
        raise HTTPException(status_code=404, detail="Resource not found")


def require_conversation_access(db: Session, user: User, conversation_id: str) -> Conversation:
    conversation = db.get(Conversation, conversation_id)
    if not conversation or conversation.user_id != user.id:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return conversation


def require_memory_access(db: Session, user: User, memory_id: str) -> Memory:
    memory = db.get(Memory, memory_id)
    if not memory or memory.user_id != user.id:
        raise HTTPException(status_code=404, detail="Memory not found")
    return memory


def require_project_access(db: Session, user: User, project_id: str) -> Project:
    project = db.get(Project, project_id)
    if not project or project.user_id != user.id:
        raise HTTPException(status_code=404, detail="Project not found")
    return project


def require_file_access(db: Session, user: User, file_id: str) -> File:
    file = db.get(File, file_id)
    if not file or file.user_id != user.id:
        raise HTTPException(status_code=404, detail="File not found")
    return file


def require_agent_access(db: Session, user: User, agent_id: str) -> Agent:
    agent = db.get(Agent, agent_id)
    if not agent or agent.user_id != user.id:
        raise HTTPException(status_code=404, detail="Agent not found")
    return agent
