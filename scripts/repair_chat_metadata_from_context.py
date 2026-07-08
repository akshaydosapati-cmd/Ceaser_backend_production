from __future__ import annotations

from app.agents.registry import AgentRegistry
from app.core.database.session import SessionLocal
from app.models.conversation import Conversation, Message
from app.services.orchestrator.agent_selector import AgentSelector
from app.services.orchestrator.contribution_merger import ContributionMerger
from app.services.orchestrator.context_builder import ContextBuilder
from app.services.orchestrator.memory_retriever import MemoryRetriever
from app.services.orchestrator.workspace_resolver import WorkspaceResolver


def previous_user_message(messages: list[Message], index: int) -> Message | None:
    for previous in reversed(messages[:index]):
        if previous.role == "user":
            return previous
    return None


def main() -> None:
    db = SessionLocal()
    try:
        workspace_resolver = WorkspaceResolver(db)
        memory_retriever = MemoryRetriever(db)
        agent_selector = AgentSelector()
        registry = AgentRegistry()
        merger = ContributionMerger()
        context_builder = ContextBuilder(db)
        repaired = 0

        conversations = db.query(Conversation).all()
        for conversation in conversations:
            messages = sorted(conversation.messages, key=lambda message: message.created_at)
            for index, message in enumerate(messages):
                if message.role != "assistant":
                    continue
                user_message = previous_user_message(messages, index)
                if not user_message:
                    continue

                workspace_context = workspace_resolver.resolve(conversation.workspace_id)
                memories = memory_retriever.retrieve_relevant_memories(
                    workspace_id=conversation.workspace_id,
                    query=user_message.content,
                )
                selected_agents = agent_selector.select_agents(
                    message=user_message.content,
                    enabled_agents=workspace_context["enabled_agents"],
                )
                selected_agent_names = [agent["name"] for agent in selected_agents]
                context = context_builder.build_context(
                    workspace_context=workspace_context,
                    memories=memories,
                    selected_agents=selected_agents,
                    conversation_id=conversation.id,
                )
                context["message"] = user_message.content
                contributions = [agent.contribute(context) for agent in registry.load_many(selected_agent_names)]
                merged = merger.merge(selected_agents=selected_agent_names, contributions=contributions)

                current = message.extra_metadata or {}
                message.extra_metadata = {
                    **current,
                    "workspace": workspace_context["workspace"]["type"],
                    "selected_agents": selected_agent_names,
                    "contributions": contributions,
                    "contribution_summary": merged["summary"],
                    "memories_used": memories,
                    "context_summary": {
                        **current.get("context_summary", {}),
                        "workspace_id": conversation.workspace_id,
                        "workspace_name": workspace_context["workspace"]["name"],
                        "memory_count": len(memories),
                        "repaired_from_context": True,
                    },
                }
                repaired += 1
        db.commit()
        print(f"Repaired metadata for {repaired} assistant messages.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
