from __future__ import annotations

from sqlalchemy.orm import Session

from app.repositories.conversation_repository import ConversationRepository
from app.repositories.project_repository import ProjectRepository
from app.services.integrations.integration_context_service import IntegrationContextService


class ContextBuilder:
    def __init__(self, db: Session):
        self.conversations = ConversationRepository(db)
        self.projects = ProjectRepository(db)
        self.integrations = IntegrationContextService(db)

    def build_context(
        self,
        user_context: dict,
        memories: list[dict],
        selected_agents: list[dict],
        conversation_id: str | None = None,
        message_limit: int = 20,
    ) -> dict:
        user_id = user_context["scope"]["id"]
        projects = [
            {
                "id": project.id,
                "name": project.name,
                "description": project.description,
                "status": project.status,
            }
            for project in self.projects.list(user_id=user_id)[:5]
        ]
        messages = []
        if conversation_id:
            messages = [
                {
                    "id": message.id,
                    "role": message.role,
                    "content": message.content,
                    "created_at": message.created_at.isoformat(),
                }
                for message in self.conversations.list_messages(conversation_id=conversation_id)[-message_limit:]
            ]
        integration_context = {
            agent["name"]: self.integrations.for_agent(user_id=user_id, agent_name=agent["name"])
            for agent in selected_agents
        }
        return {
            "scope": user_context["scope"],
            "memories": memories,
            "projects": projects,
            "integrations": integration_context,
            "goals": [],
            "conversation": messages,
            "enabled_agents": user_context["enabled_agents"],
            "selected_agents": selected_agents,
        }
