from __future__ import annotations

import re
import asyncio
import threading
from dataclasses import asdict, replace
from time import perf_counter
from typing import Any
from datetime import date, datetime, timedelta

from sqlalchemy.orm import Session

from app.agents.registry import AgentRegistry
from app.engines.research_engine import ResearchEngine
from app.models.conversation import Conversation, Message
from app.models.project import Project, ProjectMember
from app.models.user import User
from app.repositories.file_repository import FileRepository
from app.services.conversation_service import ConversationService
from app.services.orchestrator.context_builder import ContextBuilder
from app.services.orchestrator.memory_capture import MemoryCapture
from app.services.orchestrator.memory_retriever import MemoryRetriever
from app.services.orchestrator.knowledge_router import KnowledgeRoute, KnowledgeRouter
from app.services.orchestrator.response_pipeline import ResponsePipeline
from app.services.orchestrator.suggestion_engine import SuggestionEngine
from app.services.project_service import ProjectService
from app.services.orchestrator.user_context_resolver import UserContextResolver
from app.services.workflows import WorkflowOrchestrator
from app.services.integrations import IntegrationManager
from app.intelligence.knowledge.context_builder import context_builder as intelligence_context_builder
from app.intelligence.knowledge.engine import KnowledgeEngine
from app.intelligence.knowledge.repository import KnowledgeRepository
from app.intelligence.orchestrator.intent_engine import intent_engine
from app.intelligence.orchestrator.models import IntentType
from app.intelligence.orchestrator.models import RequestContext
from app.intelligence.orchestrator.retrieval_planner import retrieval_planner


class CeaserOrchestrator:
    def __init__(self, db: Session):
        self.db = db
        self.user_context_resolver = UserContextResolver(db)
        self.memory_retriever = MemoryRetriever(db)
        self.knowledge_router = KnowledgeRouter()
        self.agent_registry = AgentRegistry()
        self.context_builder = ContextBuilder(db)
        self.memory_capture = MemoryCapture(db)
        self.conversations = ConversationService(db)
        self.research_engine = ResearchEngine()
        self.files = FileRepository(db)
        self.workflow_orchestrator = WorkflowOrchestrator(db)
        self.response_pipeline = ResponsePipeline()
        self.suggestion_engine = SuggestionEngine()

    def handle_message(
        self,
        user_id: str,
        message: str,
        conversation_id: str | None = None,
        file_ids: list[str] | None = None,
        *,
        request_id: str | None = None,
        parent_message_id: str | None = None,
    ) -> dict:
        attached_documents = self._attached_documents(user_id=user_id, file_ids=file_ids or [])
        effective_message = message
        if attached_documents:
            names = ", ".join(document["name"] for document in attached_documents)
            effective_message = f"{message}\n\nAttached document(s): {names}"

        conversation = self._get_conversation(conversation_id)
        conversation_context = self._conversation_context(conversation)
        follow_up_trace = self._follow_up_trace(
            message=message,
            conversation_context=conversation_context,
            parent_message_id=parent_message_id,
        )
        effective_message = self._contextualize_follow_up(effective_message, follow_up_trace)
        route_decision = self.knowledge_router.classify(
            message=message,
            has_attached_files=bool(attached_documents),
            is_follow_up=bool(follow_up_trace.get("follow_up_detected")),
        )
        if conversation:
            self.conversations.create_message(
                conversation_id=conversation.id,
                role="user",
                content=message,
                metadata={
                    "request_id": request_id,
                    "parent_message_id": parent_message_id,
                    "attached_files": [{"id": item["id"], "name": item["name"], "file_type": item["file_type"]} for item in attached_documents],
                    "follow_up_detected": follow_up_trace["follow_up_detected"],
                    "active_topic": follow_up_trace["active_topic"],
                    "active_subtopic": follow_up_trace.get("active_subtopic"),
                    "last_user_intent": follow_up_trace.get("follow_up_intent"),
                    "resolved_entities": follow_up_trace["resolved_entities"],
                    "context_source": follow_up_trace["context_source"],
                },
                ingest_knowledge=False,
            )
            if conversation.title == "New Chat":
                self.conversations.rename(conversation, self.conversations.generate_title(message))

        # Integration routing must use the user's actual text, never the
        # contextual prompt wrapper added for a follow-up response.
        calendar_response = self._maybe_calendar_response(user_id=user_id, message=message) if route_decision.route is KnowledgeRoute.CALENDAR else None
        if calendar_response:
            return self._direct_response(
                user_id=user_id,
                conversation=conversation,
                conversation_id=conversation_id,
                conversation_context=conversation_context,
                follow_up_trace=follow_up_trace,
                response=calendar_response,
                selected_agents=["Alex"],
                workflow_type="calendar_lookup",
                summary="Calendar lookup completed.",
                request_id=request_id,
                parent_message_id=parent_message_id,
            )

        integration_response = self._maybe_integration_response(user_id=user_id, message=message) if route_decision.route is KnowledgeRoute.INTEGRATION else None
        if integration_response:
            return self._direct_response(
                user_id=user_id,
                conversation=conversation,
                conversation_id=conversation_id,
                conversation_context=conversation_context,
                follow_up_trace=follow_up_trace,
                response=integration_response,
                selected_agents=["Alex"],
                workflow_type="integration_lookup",
                summary="Integration lookup completed.",
                request_id=request_id,
                parent_message_id=parent_message_id,
            )

        project_members_response = self._maybe_project_members_response(user_id=user_id, message=message) if route_decision.route is KnowledgeRoute.MEMORY else None
        if project_members_response:
            return self._direct_response(
                user_id=user_id,
                conversation=conversation,
                conversation_id=conversation_id,
                conversation_context=conversation_context,
                follow_up_trace=follow_up_trace,
                response=project_members_response,
                selected_agents=["Bolt"],
                workflow_type="project_members_lookup",
                summary="Project members lookup completed.",
                request_id=request_id,
                parent_message_id=parent_message_id,
            )

        identity_memory_response = self._maybe_identity_memory_response(user_id=user_id, message=message) if route_decision.route is KnowledgeRoute.MEMORY else None
        if identity_memory_response:
            return self._direct_response(
                user_id=user_id,
                conversation=conversation,
                conversation_id=conversation_id,
                conversation_context=conversation_context,
                follow_up_trace=follow_up_trace,
                response=identity_memory_response,
                selected_agents=["Alex"],
                workflow_type="memory_identity",
                summary="Identity memory updated.",
                request_id=request_id,
                parent_message_id=parent_message_id,
            )

        workflow = None
        if self._is_explicit_workflow_creation_request(message):
            workflow = self.workflow_orchestrator.run(user_id=user_id, message=message, conversation_id=conversation_id, file_ids=file_ids or [])
        selected_agent_names = workflow.selected_agents if workflow else self._default_stream_agents(message)
        report_request = self._is_report_request(message)
        research_result = self._maybe_research(query=self._research_query(message, conversation_context), selected_agent_names=selected_agent_names) if route_decision.route is KnowledgeRoute.RESEARCH else None
        lightweight_follow_up = route_decision.route is KnowledgeRoute.FOLLOW_UP
        lightweight_normal = route_decision.route in {KnowledgeRoute.GENERAL, KnowledgeRoute.DESKTOP} and not self._requires_rich_context(message)
        knowledge_context = self._lightweight_follow_up_context(follow_up_trace) if lightweight_follow_up else self._minimal_chat_context() if lightweight_normal else self._knowledge_context(
            user_id=user_id,
            message=effective_message,
            conversation_id=conversation.id if conversation else conversation_id,
        )
        memories = [] if lightweight_follow_up or lightweight_normal else self.memory_retriever.retrieve_relevant_memories(user_id=user_id, query=message)
        captured_memories = self.memory_capture.capture(user_id=user_id, message=message)
        final_response = self.response_pipeline.generate(
            message=message,
            context={
                "scope": {"name": "CEASER", "type": "personal_ai_os"},
                "current_message": message,
                "latest_user_message": message,
                "resolved_request_context": effective_message,
                "memories": memories,
                "conversation": self._follow_up_generation_context(conversation_context, follow_up_trace) if lightweight_follow_up else [] if lightweight_normal else conversation_context["messages"],
                "conversation_summary": None if lightweight_normal else conversation_context.get("summary"),
                "previous_research": conversation_context["previous_research"],
                "projects": [],
                "documents": attached_documents,
                "knowledge_context": knowledge_context,
                "follow_up_trace": follow_up_trace,
                "merged_contributions": {
                    "selected_agents": selected_agent_names,
                    "contributions": workflow.contributions if workflow else [],
                    "summary": workflow.result_summary if workflow else "",
                    "workflow_response": workflow.final_response if workflow else "",
                },
                "report_request": report_request,
                "research_result": research_result.model_dump() if research_result else None,
            },
        )
        captured_response_memories = self.memory_capture.capture_interaction(
            user_id=user_id,
            user_message=message,
            assistant_response=final_response,
        )
        suggestions = self._generate_suggestions(
            user_query=message,
            response_text=final_response,
            conversation=conversation,
            conversation_context=conversation_context,
            intent=knowledge_context.get("intent"),
            retrieval_scope=knowledge_context.get("retrieval_scope"),
            output_format=knowledge_context.get("output_format"),
            intent_domain=knowledge_context.get("intent_domain"),
            intent_subdomain=knowledge_context.get("intent_subdomain"),
            request_id=request_id,
            parent_message_id=parent_message_id,
            active_topic=follow_up_trace.get("active_topic"),
        )
        response_payload = {
            "scope": "personal_ai_os",
            "conversation_id": conversation.id if conversation else conversation_id,
            "selected_agents": selected_agent_names,
            "contributions": workflow.contributions if workflow else [],
            "contribution_summary": workflow.result_summary if workflow else "Response generated.",
            "memories_used": memories,
            "research": research_result.model_dump() if research_result else None,
            "workflow": {
                "id": workflow.workflow_id,
                "type": workflow.workflow_type,
                "status": workflow.status,
                "steps": workflow.steps,
                "summary": workflow.result_summary,
            } if workflow else None,
            "context_summary": {
                "user_id": user_id,
                "scope_name": "CEASER",
                "memory_count": len(memories),
                "project_count": 0,
                "conversation_message_count": len(conversation_context["messages"]),
                "enabled_agent_count": len(selected_agent_names),
                "captured_memory_count": len(captured_memories) + len(captured_response_memories),
                "attached_document_count": len(attached_documents),
                "workflow_id": workflow.workflow_id if workflow else None,
                "request_id": request_id,
                "parent_message_id": parent_message_id,
                "history_message_count": conversation_context.get("history_message_count", 0),
                "history_token_count": conversation_context.get("history_token_count", 0),
                "follow_up_detected": follow_up_trace.get("follow_up_detected", False),
                "active_topic": follow_up_trace.get("active_topic"),
                "resolved_entities": follow_up_trace.get("resolved_entities", []),
                "context_source": follow_up_trace.get("context_source", []),
            },
            "suggestions": [asdict(item) for item in suggestions],
            "response": final_response,
        }
        if conversation:
            assistant_message = self.conversations.create_message(
                conversation_id=conversation.id,
                role="assistant",
                content=final_response,
                metadata={key: value for key, value in response_payload.items() if key not in {"conversation_id", "response"}},
                ingest_knowledge=False,
            )
            bound = self._bind_suggestions(
                suggestions=suggestions,
                conversation_id=conversation.id,
                parent_message_id=assistant_message.id,
                active_topic=follow_up_trace.get("active_topic"),
            )
            response_payload["suggestions"] = [asdict(item) for item in bound]
            assistant_message.extra_metadata = {
                **(assistant_message.extra_metadata or {}),
                **{key: value for key, value in response_payload.items() if key not in {"conversation_id", "response"}},
            }
            self.db.add(assistant_message)
            self.db.commit()
            self.db.refresh(assistant_message)
        return response_payload

    def prepare_stream_request(
        self,
        user_id: str,
        message: str,
        conversation_id: str | None = None,
        file_ids: list[str] | None = None,
        *,
        request_id: str | None = None,
        parent_message_id: str | None = None,
    ) -> dict[str, Any]:
        started = perf_counter()
        request_trace: dict[str, Any] = {}
        attached_documents = self._attached_documents(user_id=user_id, file_ids=file_ids or [], trace=request_trace)
        effective_message = message
        if attached_documents:
            names = ", ".join(document["name"] for document in attached_documents)
            effective_message = f"{message}\n\nAttached document(s): {names}"
        is_file_summary_request = self._looks_like_file_summary_request(effective_message, attached_documents)
        if is_file_summary_request:
            attached_documents = self._attached_documents(
                user_id=user_id,
                file_ids=file_ids or [],
                include_content=False,
                trace=request_trace,
            )

        conversation = self._get_conversation(conversation_id)
        conversation_context = self._conversation_context(conversation)
        follow_up_trace = self._follow_up_trace(
            message=message,
            conversation_context=conversation_context,
            parent_message_id=parent_message_id,
        )
        effective_message = self._contextualize_follow_up(effective_message, follow_up_trace)
        route_decision = self.knowledge_router.classify(
            message=message,
            has_attached_files=bool(attached_documents),
            is_follow_up=bool(follow_up_trace.get("follow_up_detected")),
        )

        if conversation:
            self.conversations.create_message(
                conversation_id=conversation.id,
                role="user",
                content=message,
                metadata={
                    "request_id": request_id,
                    "parent_message_id": parent_message_id,
                    "attached_files": [{"id": item["id"], "name": item["name"], "file_type": item["file_type"]} for item in attached_documents],
                    "follow_up_detected": follow_up_trace["follow_up_detected"],
                    "active_topic": follow_up_trace["active_topic"],
                    "active_subtopic": follow_up_trace.get("active_subtopic"),
                    "last_user_intent": follow_up_trace.get("follow_up_intent"),
                    "resolved_entities": follow_up_trace["resolved_entities"],
                    "context_source": follow_up_trace["context_source"],
                },
                ingest_knowledge=False,
            )
            if conversation.title == "New Chat":
                self.conversations.rename(conversation, self.conversations.generate_title(message))

        calendar_response = self._maybe_calendar_response(user_id=user_id, message=message) if route_decision.route is KnowledgeRoute.CALENDAR else None
        if calendar_response:
            return {
                "mode": "direct",
                "user_id": user_id,
                "conversation": conversation,
                "conversation_id": conversation.id if conversation else conversation_id,
                "conversation_context": conversation_context,
                "follow_up_trace": follow_up_trace,
                "response": calendar_response,
                "selected_agents": ["Alex"],
                "workflow_type": "calendar_lookup",
                "summary": "Calendar lookup completed.",
                "request_id": request_id,
                "parent_message_id": parent_message_id,
            }

        integration_response = self._maybe_integration_response(user_id=user_id, message=message) if route_decision.route is KnowledgeRoute.INTEGRATION else None
        if integration_response:
            return {
                "mode": "direct",
                "user_id": user_id,
                "conversation": conversation,
                "conversation_id": conversation.id if conversation else conversation_id,
                "conversation_context": conversation_context,
                "follow_up_trace": follow_up_trace,
                "response": integration_response,
                "selected_agents": ["Alex"],
                "workflow_type": "integration_lookup",
                "summary": "Integration lookup completed.",
                "request_id": request_id,
                "parent_message_id": parent_message_id,
            }

        project_members_response = self._maybe_project_members_response(user_id=user_id, message=message) if route_decision.route is KnowledgeRoute.MEMORY else None
        if project_members_response:
            return {
                "mode": "direct",
                "user_id": user_id,
                "conversation": conversation,
                "conversation_id": conversation.id if conversation else conversation_id,
                "conversation_context": conversation_context,
                "follow_up_trace": follow_up_trace,
                "response": project_members_response,
                "selected_agents": ["Bolt"],
                "workflow_type": "project_members_lookup",
                "summary": "Project members lookup completed.",
                "request_id": request_id,
                "parent_message_id": parent_message_id,
            }

        identity_memory_response = self._maybe_identity_memory_response(user_id=user_id, message=message) if route_decision.route is KnowledgeRoute.MEMORY else None
        if identity_memory_response:
            return {
                "mode": "direct",
                "user_id": user_id,
                "conversation": conversation,
                "conversation_id": conversation.id if conversation else conversation_id,
                "conversation_context": conversation_context,
                "follow_up_trace": follow_up_trace,
                "response": identity_memory_response,
                "selected_agents": ["Alex"],
                "workflow_type": "memory_identity",
                "summary": "Identity memory updated.",
                "request_id": request_id,
                "parent_message_id": parent_message_id,
            }

        selected_agent_names: list[str] = []
        report_request = self._is_report_request(message)
        workflow = None
        research_result = None
        routing_started = perf_counter()
        if self._is_explicit_workflow_creation_request(message):
            workflow = self.workflow_orchestrator.run(
                user_id=user_id,
                message=message,
                conversation_id=conversation_id,
                file_ids=file_ids or [],
            )
            selected_agent_names = workflow.selected_agents
            if route_decision.route is KnowledgeRoute.RESEARCH and self._should_run_research(message, selected_agent_names):
                research_result = self._maybe_research(query=self._research_query(message, conversation_context), selected_agent_names=selected_agent_names)
        else:
            selected_agent_names = self._default_stream_agents(message)

        routing_finished = perf_counter()
        tool_calls_started = perf_counter()
        if not research_result and route_decision.route is KnowledgeRoute.RESEARCH:
            research_result = self._maybe_research(
                query=self._research_query(message, conversation_context),
                selected_agent_names=selected_agent_names,
            )
        tool_calls_finished = perf_counter()

        lightweight_follow_up = route_decision.route is KnowledgeRoute.FOLLOW_UP
        lightweight_normal = route_decision.route in {KnowledgeRoute.GENERAL, KnowledgeRoute.DESKTOP} and not self._requires_rich_context(message)
        retrieval_started = perf_counter()
        knowledge_context = self._lightweight_follow_up_context(follow_up_trace) if lightweight_follow_up else self._minimal_chat_context() if lightweight_normal else self._knowledge_context(
            user_id=user_id,
            message=effective_message,
            conversation_id=conversation.id if conversation else conversation_id,
            file_ids=file_ids or [],
        )
        skip_memory_retrieval = lightweight_follow_up or lightweight_normal or is_file_summary_request or knowledge_context.get("retrieval_scope") in {"none", "conversation_only", "web", "integrations"}
        memories = [] if skip_memory_retrieval else self.memory_retriever.retrieve_relevant_memories(user_id=user_id, query=effective_message)
        retrieval_finished = perf_counter()
        captured_memories = self.memory_capture.capture(user_id=user_id, message=message)
        observability = {
            "prepare_ms": round((perf_counter() - started) * 1000, 2),
            "routing_ms": round((routing_finished - routing_started) * 1000, 2),
            "tool_calls_ms": round((tool_calls_finished - tool_calls_started) * 1000, 2),
            "retrieval_time_ms": round((retrieval_finished - retrieval_started) * 1000, 2),
            "intent_ms": knowledge_context.get("_intent_ms"),
            "context_tokens": knowledge_context.get("_context_tokens"),
            "retrieval_scope": knowledge_context.get("retrieval_scope"),
            "context_mode": "follow_up" if lightweight_follow_up else "minimal" if lightweight_normal else "retrieval",
            "knowledge_route": route_decision.route.value,
            "knowledge_route_reason": route_decision.reason,
            "retrieval_sources": knowledge_context.get("retrieval_sources", []),
            "file_lookup_ms": request_trace.get("file_lookup_ms") or knowledge_context.get("file_lookup_ms"),
            "permission_check_ms": request_trace.get("permission_check_ms"),
            "document_metadata_load_ms": knowledge_context.get("document_metadata_load_ms"),
            "chunk_load_ms": knowledge_context.get("chunk_load_ms"),
            "vector_search_ms": knowledge_context.get("vector_search_ms"),
            "keyword_search_ms": knowledge_context.get("keyword_search_ms"),
            "rerank_ms": knowledge_context.get("rerank_ms"),
            "context_build_ms": knowledge_context.get("context_build_ms"),
            "prompt_tokens": knowledge_context.get("prompt_tokens"),
            "selected_chunks": knowledge_context.get("selected_chunks"),
            "cache_hit": knowledge_context.get("cache_hit"),
        }
        return {
            "mode": "generate",
            "user_id": user_id,
            "message": message,
            "effective_message": effective_message,
            "conversation": conversation,
            "conversation_id": conversation.id if conversation else conversation_id,
            "conversation_context": conversation_context,
            "attached_documents": attached_documents,
            "selected_agents": selected_agent_names,
            "workflow": workflow,
            "research_result": research_result,
            "memories": memories,
            "knowledge_context": knowledge_context,
            "captured_memories": captured_memories,
            "observability": observability,
            "request_id": request_id,
            "parent_message_id": parent_message_id,
            "follow_up_trace": follow_up_trace,
            "context": {
                "scope": {"name": "CEASER", "type": "personal_ai_os"},
                "current_message": message,
                "latest_user_message": message,
                "resolved_request_context": effective_message,
                "memories": memories,
                "conversation": self._follow_up_generation_context(conversation_context, follow_up_trace) if lightweight_follow_up else [] if lightweight_normal else conversation_context["messages"],
                "conversation_summary": None if lightweight_normal else conversation_context.get("summary"),
                "previous_research": conversation_context["previous_research"],
                "projects": [],
                "documents": attached_documents,
                "knowledge_context": knowledge_context,
                "follow_up_trace": follow_up_trace,
                "merged_contributions": {
                    "selected_agents": selected_agent_names,
                    "contributions": workflow.contributions if workflow else [],
                    "summary": workflow.result_summary if workflow else "",
                    "workflow_response": workflow.final_response if workflow else "",
                },
                "report_request": report_request,
                "research_result": research_result.model_dump() if research_result else None,
            },
        }

    def begin_stream_response(self, prepared: dict[str, Any]) -> Message | None:
        """Create a durable assistant message before a long stream finishes."""
        conversation = prepared.get("conversation")
        if not conversation:
            return None
        return self.conversations.create_message(
            conversation_id=conversation.id,
            role="assistant",
            content="",
            metadata={
                "streaming": True,
                "request_id": prepared.get("request_id"),
                "parent_message_id": prepared.get("parent_message_id"),
            },
            ingest_knowledge=False,
        )

    def persist_stream_response(self, assistant_message: Message | None, content: str) -> None:
        """Checkpoint partial text so a browser refresh never loses a stream."""
        if not assistant_message or not content:
            return
        assistant_message.content = content
        self.db.add(assistant_message)
        self.db.commit()
        self.db.refresh(assistant_message)

    def finalize_stream_response(self, prepared: dict[str, Any], final_response: str, assistant_message: Message | None = None) -> dict[str, Any]:
        if prepared["mode"] == "direct":
            return self._direct_response(
                user_id=prepared["user_id"],
                conversation=prepared["conversation"],
                conversation_id=prepared["conversation_id"],
                conversation_context=prepared["conversation_context"],
                follow_up_trace=prepared.get("follow_up_trace") or {},
                response=prepared["response"],
                selected_agents=prepared["selected_agents"],
                workflow_type=prepared["workflow_type"],
                summary=prepared["summary"],
                request_id=prepared.get("request_id"),
                parent_message_id=prepared.get("parent_message_id"),
            )

        if self.response_pipeline.requires_structured_response(prepared.get("context", {})):
            final_response = self.response_pipeline.normalize_structured_response(
                final_response,
                project_report=bool(prepared.get("context", {}).get("report_request")),
            )

        workflow = prepared.get("workflow")
        follow_up_trace = prepared.get("follow_up_trace") or {}
        captured_response_memories = self.memory_capture.capture_interaction(
            user_id=prepared["user_id"],
            user_message=prepared["message"],
            assistant_response=final_response,
        )
        suggestions = self._generate_suggestions(
            user_query=prepared["message"],
            response_text=final_response,
            conversation=prepared.get("conversation"),
            conversation_context=prepared.get("conversation_context"),
            intent=prepared.get("knowledge_context", {}).get("intent"),
            retrieval_scope=prepared.get("observability", {}).get("retrieval_scope"),
            output_format=prepared.get("knowledge_context", {}).get("output_format"),
            intent_domain=prepared.get("knowledge_context", {}).get("intent_domain"),
            intent_subdomain=prepared.get("knowledge_context", {}).get("intent_subdomain"),
            request_id=prepared.get("request_id"),
            parent_message_id=prepared.get("parent_message_id"),
            active_topic=follow_up_trace.get("active_topic"),
        )
        response_payload = {
            "scope": "personal_ai_os",
            "conversation_id": prepared["conversation_id"],
            "selected_agents": prepared["selected_agents"],
            "contributions": workflow.contributions if workflow else [],
            "contribution_summary": workflow.result_summary if workflow else "Response generated.",
            "memories_used": prepared["memories"],
            "research": prepared["research_result"].model_dump() if prepared.get("research_result") else None,
            "workflow": {
                "id": workflow.workflow_id,
                "type": workflow.workflow_type,
                "status": workflow.status,
                "steps": workflow.steps,
                "summary": workflow.result_summary,
            } if workflow else None,
            "context_summary": {
                "user_id": prepared["user_id"],
                "scope_name": "CEASER",
                "memory_count": len(prepared["memories"]),
                "project_count": 0,
                "conversation_message_count": len(prepared["conversation_context"]["messages"]),
                "enabled_agent_count": len(prepared["selected_agents"]),
                "captured_memory_count": len(prepared["captured_memories"]) + len(captured_response_memories),
                "attached_document_count": len(prepared["attached_documents"]),
                "workflow_id": workflow.workflow_id if workflow else None,
                "provider": prepared.get("stream_trace", {}).get("provider"),
                "model": prepared.get("stream_trace", {}).get("model"),
                "fallback_used": prepared.get("stream_trace", {}).get("fallback_used"),
                "fallback_from": prepared.get("stream_trace", {}).get("fallback_from"),
                "request_id": prepared.get("request_id") or prepared.get("stream_trace", {}).get("request_id"),
                "parent_message_id": prepared.get("parent_message_id"),
                "upstream_ttft_ms": prepared.get("stream_trace", {}).get("first_token_ms"),
                "endpoint_ttft_ms": prepared.get("stream_trace", {}).get("endpoint_ttft_ms"),
                "total_time_ms": prepared.get("stream_trace", {}).get("total_time_ms"),
                "context_tokens": prepared.get("stream_trace", {}).get("context_tokens") or prepared.get("observability", {}).get("context_tokens"),
                "output_tokens": prepared.get("stream_trace", {}).get("output_tokens"),
                "retrieval_time_ms": prepared.get("stream_trace", {}).get("retrieval_time_ms") or prepared.get("observability", {}).get("retrieval_time_ms"),
                "provider_connect_ms": prepared.get("stream_trace", {}).get("provider_connect_ms"),
                "provider_generation_ms": prepared.get("stream_trace", {}).get("provider_generation_ms"),
                "retrieval_scope": prepared.get("observability", {}).get("retrieval_scope"),
                "retrieval_sources": prepared.get("observability", {}).get("retrieval_sources", []),
                "file_lookup_ms": prepared.get("observability", {}).get("file_lookup_ms"),
                "permission_check_ms": prepared.get("observability", {}).get("permission_check_ms"),
                "document_metadata_load_ms": prepared.get("observability", {}).get("document_metadata_load_ms"),
                "chunk_load_ms": prepared.get("observability", {}).get("chunk_load_ms"),
                "vector_search_ms": prepared.get("observability", {}).get("vector_search_ms"),
                "keyword_search_ms": prepared.get("observability", {}).get("keyword_search_ms"),
                "rerank_ms": prepared.get("observability", {}).get("rerank_ms"),
                "context_build_ms": prepared.get("observability", {}).get("context_build_ms"),
                "prompt_tokens": prepared.get("stream_trace", {}).get("prompt_tokens") or prepared.get("observability", {}).get("prompt_tokens"),
                "selected_chunks": prepared.get("observability", {}).get("selected_chunks"),
                "cache_hit": prepared.get("observability", {}).get("cache_hit"),
                "history_message_count": prepared.get("conversation_context", {}).get("history_message_count", 0),
                "history_token_count": prepared.get("conversation_context", {}).get("history_token_count", 0),
                "follow_up_detected": follow_up_trace.get("follow_up_detected", False),
                "active_topic": follow_up_trace.get("active_topic"),
                "resolved_entities": follow_up_trace.get("resolved_entities", []),
                "context_source": follow_up_trace.get("context_source", []),
            },
            "suggestions": [asdict(item) for item in suggestions],
            "response": final_response,
        }
        conversation = prepared.get("conversation")
        if conversation:
            if assistant_message is None:
                assistant_message = self.conversations.create_message(
                    conversation_id=conversation.id,
                    role="assistant",
                    content=final_response,
                    metadata={key: value for key, value in response_payload.items() if key not in {"conversation_id", "response"}},
                    ingest_knowledge=False,
                )
            else:
                assistant_message.content = final_response
            bound = self._bind_suggestions(
                suggestions=suggestions,
                conversation_id=conversation.id,
                parent_message_id=assistant_message.id,
                active_topic=follow_up_trace.get("active_topic"),
            )
            response_payload["suggestions"] = [asdict(item) for item in bound]
            assistant_message.extra_metadata = {
                **(assistant_message.extra_metadata or {}),
                "streaming": False,
                **{key: value for key, value in response_payload.items() if key not in {"conversation_id", "response"}},
            }
            self.db.add(assistant_message)
            self.db.commit()
            self.db.refresh(assistant_message)
        return response_payload

    def _knowledge_context(self, *, user_id: str, message: str, conversation_id: str | None, file_ids: list[str] | None = None) -> dict:
        async def build() -> dict:
            started = perf_counter()
            repository = KnowledgeRepository(self.db)
            document_metadata_started = perf_counter()
            source = repository.find_source_by_file_id(user_id=user_id, file_id=file_ids[0]) if file_ids else None
            request = RequestContext(
                user_id=user_id,
                message=message,
                conversation_id=conversation_id,
                interaction_mode="chat",
                source_id=source.id if source else None,
                selected_file_ids=file_ids or [],
                metadata={"rag_trace": {}},
            )
            intent_started = perf_counter()
            intent = await intent_engine.classify(request)
            intent_finished = perf_counter()
            plan = await retrieval_planner.build(request=request, intent=intent)
            retrieval_started = perf_counter()
            items = await KnowledgeEngine(self.db).retrieve(request=request, plan=plan)
            retrieval_finished = perf_counter()
            context_started = perf_counter()
            token_budget = 1800 if intent == IntentType.FILE_SUMMARY else 6000
            package = intelligence_context_builder.build(request=request, items=items, token_budget=token_budget)
            rag_trace = request.metadata.get("rag_trace", {})
            return {
                "intent": intent.value,
                "output_format": plan.output_format,
                "evidence": package.evidence_text,
                "source_count": len(package.items),
                "retrieval_scope": plan.retrieval_scope,
                "retrieval_sources": plan.retrieval_sources,
                "intent_domain": request.metadata.get("intent_domain"),
                "intent_subdomain": request.metadata.get("intent_subdomain"),
                "_intent_ms": round((intent_finished - intent_started) * 1000, 2),
                "_retrieval_ms": round((retrieval_finished - retrieval_started) * 1000, 2),
                "_context_total_ms": round((perf_counter() - started) * 1000, 2),
                "_context_tokens": max(1, round(len(package.evidence_text or "") / 4)),
                "document_metadata_load_ms": round((perf_counter() - document_metadata_started) * 1000, 2),
                "file_lookup_ms": rag_trace.get("file_lookup_ms"),
                "chunk_load_ms": rag_trace.get("chunk_load_ms"),
                "vector_search_ms": rag_trace.get("vector_search_ms"),
                "keyword_search_ms": rag_trace.get("keyword_search_ms"),
                "rerank_ms": rag_trace.get("rerank_ms"),
                "context_build_ms": round((perf_counter() - context_started) * 1000, 2),
                "prompt_tokens": max(1, round(len(package.evidence_text or "") / 4)),
                "selected_chunks": rag_trace.get("selected_chunks", len(package.items)),
                "cache_hit": rag_trace.get("cache_hit", False),
            }

        try:
            return self._run_async_blocking(build())
        except Exception:
            return {
                "intent": "unavailable",
                "output_format": "chat",
                "evidence": "",
                "source_count": 0,
                "retrieval_scope": "mixed",
                "retrieval_sources": [],
            }

    def _run_async_blocking(self, coro):
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(coro)

        result: dict[str, Any] = {}
        error: list[Exception] = []

        def runner() -> None:
            try:
                result["value"] = asyncio.run(coro)
            except Exception as exc:  # noqa: BLE001
                error.append(exc)

        thread = threading.Thread(target=runner, daemon=True)
        thread.start()
        thread.join()
        if error:
            raise error[0]
        return result.get("value")

    def _direct_response(
        self,
        user_id: str,
        conversation: Conversation | None,
        conversation_id: str | None,
        conversation_context: dict,
        follow_up_trace: dict,
        response: str,
        selected_agents: list[str],
        workflow_type: str,
        summary: str,
        request_id: str | None = None,
        parent_message_id: str | None = None,
    ) -> dict:
        suggestions = self._generate_suggestions(
            user_query=conversation_context.get("messages", [{}])[-1].get("content", "") if conversation_context.get("messages") else response,
            response_text=response,
            conversation=conversation,
            conversation_context=conversation_context,
            intent=workflow_type,
            retrieval_scope="direct",
            output_format="chat",
            intent_domain=None,
            intent_subdomain=None,
            request_id=request_id,
            parent_message_id=parent_message_id,
            active_topic=follow_up_trace.get("active_topic"),
        )
        response_payload = {
            "scope": "personal_ai_os",
            "conversation_id": conversation.id if conversation else conversation_id,
            "selected_agents": selected_agents,
            "contributions": [],
            "contribution_summary": summary,
            "memories_used": [],
            "research": None,
            "workflow": None,
            "context_summary": {
                "user_id": user_id,
                "scope_name": "CEASER",
                "memory_count": 0,
                "project_count": 0,
                "conversation_message_count": len(conversation_context["messages"]),
                "enabled_agent_count": len(selected_agents),
                "captured_memory_count": 0,
                "attached_document_count": 0,
                "workflow_id": None,
                "direct_response_type": workflow_type,
                "request_id": request_id,
                "parent_message_id": parent_message_id,
                "history_message_count": conversation_context.get("history_message_count", 0),
                "history_token_count": conversation_context.get("history_token_count", 0),
                "follow_up_detected": follow_up_trace.get("follow_up_detected", False),
                "active_topic": follow_up_trace.get("active_topic"),
                "resolved_entities": follow_up_trace.get("resolved_entities", []),
                "context_source": follow_up_trace.get("context_source", []),
            },
            "suggestions": [asdict(item) for item in suggestions],
            "response": response,
        }
        if conversation:
            assistant_message = self.conversations.create_message(
                conversation_id=conversation.id,
                role="assistant",
                content=response,
                metadata={key: value for key, value in response_payload.items() if key not in {"conversation_id", "response"}},
                ingest_knowledge=False,
            )
            bound = self._bind_suggestions(
                suggestions=suggestions,
                conversation_id=conversation.id,
                parent_message_id=assistant_message.id,
                active_topic=follow_up_trace.get("active_topic"),
            )
            response_payload["suggestions"] = [asdict(item) for item in bound]
            assistant_message.extra_metadata = {
                **(assistant_message.extra_metadata or {}),
                **{key: value for key, value in response_payload.items() if key not in {"conversation_id", "response"}},
            }
            self.db.add(assistant_message)
            self.db.commit()
            self.db.refresh(assistant_message)
        return response_payload

    def _generate_suggestions(
        self,
        *,
        user_query: str,
        response_text: str,
        conversation: Conversation | None,
        conversation_context: dict | None,
        intent: str | None,
        retrieval_scope: str | None,
        output_format: str | None,
        intent_domain: str | None = None,
        intent_subdomain: str | None = None,
        request_id: str | None = None,
        parent_message_id: str | None = None,
        active_topic: str | None = None,
    ) -> list:
        generated = self.suggestion_engine.generate(
            user_query=user_query,
            response_text=response_text,
            intent=intent,
            retrieval_scope=retrieval_scope,
            output_format=output_format,
            intent_domain=intent_domain,
            intent_subdomain=intent_subdomain,
            conversation_context=conversation_context,
            recent_suggestions=self._recent_suggestions(conversation),
        )
        return self._bind_suggestions(
            suggestions=generated,
            conversation_id=conversation.id if conversation else None,
            parent_message_id=parent_message_id,
            active_topic=active_topic,
        )

    def _bind_suggestions(
        self,
        *,
        suggestions: list,
        conversation_id: str | None,
        parent_message_id: str | None,
        active_topic: str | None,
    ) -> list:
        bound: list = []
        for item in suggestions:
            prompt = item.prompt or item.text
            if active_topic and item.action_type == "follow_up" and active_topic.lower() not in prompt.lower():
                prompt = f"{item.text} about {active_topic}"
            bound.append(
                replace(
                    item,
                    label=item.label or item.text,
                    prompt=prompt,
                    conversation_id=conversation_id,
                    parent_message_id=parent_message_id,
                    topic=active_topic,
                )
            )
        return bound

    def _recent_suggestions(self, conversation: Conversation | None) -> list[str]:
        if not conversation:
            return []
        messages = self.conversations.list_messages(conversation_id=conversation.id, limit=12)
        recent: list[str] = []
        for item in messages[-6:]:
            metadata = item.extra_metadata if isinstance(item.extra_metadata, dict) else {}
            suggestions = metadata.get("suggestions") or []
            if not isinstance(suggestions, list):
                continue
            for suggestion in suggestions:
                if isinstance(suggestion, dict) and suggestion.get("text"):
                    recent.append(str(suggestion["text"]))
                elif isinstance(suggestion, str):
                    recent.append(suggestion)
        return recent

    def _maybe_calendar_response(self, user_id: str, message: str) -> str | None:
        normalized = message.lower()
        # Planning an itinerary or suggesting meetings is not a request to
        # access a private calendar.  Calendar access is opt-in only.
        if not self._is_explicit_google_calendar_request(normalized):
            return None

        target_date = self._calendar_target_date(message)
        try:
            integration_manager = IntegrationManager(self.db)
            integration_manager.sync(user_id=user_id, provider_id="google-calendar")
            metadata = integration_manager.metadata(user_id=user_id, provider_id="google-calendar")
        except Exception:
            return (
                "I could not read Google Calendar right now. Please reconnect Google Calendar from Integrations, "
                "then try again."
            )

        if metadata.get("status") != "connected":
            return "Google Calendar is not connected yet. Connect it from Integrations, then I can read your events."

        events = metadata.get("items") or []
        matched_events = self._filter_calendar_events(events, target_date)
        date_label = f"{target_date.strftime('%B')} {target_date.day}, {target_date.year}"
        if not matched_events:
            return f"I checked your Google Calendar. You have no events on {date_label}."

        lines = [f"Here is what I found on your Google Calendar for {date_label}:"]
        for index, event in enumerate(matched_events, start=1):
            start = self._format_calendar_time(event.get("start"))
            end = self._format_calendar_time(event.get("end"))
            title = event.get("title") or "Untitled event"
            location = f" - {event.get('location')}" if event.get("location") else ""
            time_range = f"{start} - {end}" if end and end != start else start
            lines.append(f"{index}. {time_range}: {title}{location}")
        return "\n".join(lines)

    def _maybe_integration_response(self, user_id: str, message: str) -> str | None:
        normalized = message.lower()
        provider_id = None
        label = None
        # Integrations are opt-in.  A normal question, including a contextual
        # follow-up, must never be converted into an integration request just
        # because a broad keyword happens to appear.
        if self._is_explicit_google_drive_request(normalized):
            provider_id, label = "google-drive", "Google Drive"
        elif self._is_explicit_gmail_request(normalized):
            provider_id, label = "gmail", "Gmail"
        elif re.search(r"\b(?:show|list|read|find|check|sync)\b.{0,40}\b(?:google tasks|my tasks|my todo|my to-do)\b", normalized):
            provider_id, label = "google-tasks", "Google Tasks"
        elif re.search(r"\b(?:show|list|read|find|check|sync)\b.{0,40}\b(?:google classroom|my assignments|my coursework)\b", normalized):
            provider_id, label = "google-classroom", "Google Classroom"
        elif re.search(r"\b(?:show|list|read|find|search|check|sync|use|summarize|summary|explain|what|who)\b.{0,90}\b(?:notion|my notion|notion page|notion pages|notion database|notion databases|notion docs|notion workspace|notion members|notion users|workspace members|workspace users|workspace context|knowledge sources)\b", normalized):
            provider_id, label = "notion", "Notion"
        elif re.search(r"\b(?:show|list|read|find|search|check|sync|use|summarize|summary|explain|what|who)\b.{0,100}\b(?:github|git hub|repository|repositories|repo|repos|commit|commits|issue|issues|pull request|pull requests|prs|readme|codebase)\b", normalized):
            provider_id, label = "github", "GitHub"
        if not provider_id:
            return None

        try:
            integration_manager = IntegrationManager(self.db)
            integration_manager.sync(user_id=user_id, provider_id=provider_id)
            metadata = integration_manager.metadata(user_id=user_id, provider_id=provider_id)
        except Exception:
            return f"I could not read {label} right now. Please reconnect {label} from Integrations, then try again."

        if metadata.get("status") != "connected":
            return f"{label} is not connected yet. Connect it from Integrations, then I can read it."

        items = metadata.get("items") or []
        if not items:
            return f"I synced {label}. I did not find any recent items to show."

        if provider_id == "notion":
            return self._format_notion_response(message=message, normalized=normalized, metadata=metadata, items=items)
        if provider_id == "github":
            return self._format_github_response(message=message, normalized=normalized, metadata=metadata, items=items)

        lines = [f"I synced {label}. Here are the latest items:"]
        for index, item in enumerate(items[:8], start=1):
            title = (
                item.get("title")
                or item.get("subject")
                or item.get("name")
                or item.get("course_title")
                or "Untitled"
            )
            detail = item.get("from") or item.get("modified_time") or item.get("due") or item.get("status") or ""
            lines.append(f"{index}. {title}{f' - {detail}' if detail else ''}")
        return "\n".join(lines)

    def _format_github_response(self, *, message: str, normalized: str, metadata: dict, items: list[dict]) -> str:
        query = self._github_query(message)
        matched_repos = self._match_github_repos(items, query) if query else []
        repos = matched_repos or items

        if re.search(r"\b(?:commit|commits|changes|recent changes)\b", normalized):
            lines = ["I synced GitHub. Here are recent commits I can see:"]
            count = 0
            for repo in repos[:6]:
                for commit in repo.get("commits") or []:
                    count += 1
                    lines.append(f"{count}. {repo.get('full_name')}: {commit.get('message') or 'Commit'} ({commit.get('sha')})")
                    if count >= 10:
                        return "\n".join(lines)
            return "\n".join(lines) if count else "I synced GitHub, but I could not see recent commits in the visible repositories."

        if re.search(r"\b(?:issue|issues)\b", normalized):
            lines = ["I synced GitHub. Here are open issues I can see:"]
            count = 0
            for repo in repos[:6]:
                for issue in repo.get("issues") or []:
                    count += 1
                    lines.append(f"{count}. {repo.get('full_name')} #{issue.get('number')}: {issue.get('title')}")
                    if count >= 10:
                        return "\n".join(lines)
            return "\n".join(lines) if count else "I synced GitHub. I did not find open issues in the visible repositories."

        if re.search(r"\b(?:pull request|pull requests|pr|prs)\b", normalized):
            lines = ["I synced GitHub. Here are open pull requests I can see:"]
            count = 0
            for repo in repos[:6]:
                for pull_request in repo.get("pull_requests") or []:
                    count += 1
                    lines.append(f"{count}. {repo.get('full_name')} #{pull_request.get('number')}: {pull_request.get('title')}")
                    if count >= 10:
                        return "\n".join(lines)
            return "\n".join(lines) if count else "I synced GitHub. I did not find open pull requests in the visible repositories."

        if re.search(r"\b(?:readme|explain|summarize|summary|codebase|repository|repo)\b", normalized) and query and matched_repos:
            repo = matched_repos[0]
            lines = [
                f"I synced GitHub and found {repo.get('full_name')}.",
                f"Description: {repo.get('description') or 'No description provided.'}",
                f"Primary language: {repo.get('language') or 'Not specified'}",
            ]
            if repo.get("readme"):
                lines.extend(["", "README preview:", repo.get("readme")[:900]])
            commits = repo.get("commits") or []
            if commits:
                lines.extend(["", "Recent commits:"])
                lines.extend(f"- {commit.get('message') or 'Commit'}" for commit in commits[:5])
            return "\n".join(lines)

        lines = [f"I synced GitHub for {metadata.get('login') or metadata.get('account_email') or 'your account'}. These repositories are visible:"]
        for index, repo in enumerate(items[:10], start=1):
            privacy = "private" if repo.get("private") else "public"
            language = f" - {repo.get('language')}" if repo.get("language") else ""
            lines.append(f"{index}. {repo.get('full_name') or repo.get('name')} ({privacy}){language}")
        return "\n".join(lines)

    def _github_query(self, message: str) -> str | None:
        cleaned = re.sub(r"\b(?:github|git hub|my|repository|repositories|repo|repos|commit|commits|issue|issues|pull|request|requests|prs|readme|codebase|read|find|search|show|list|summarize|summary|explain|use|check|sync|what|are|is|connected|to|from|in|account|ceaser)\b", " ", message, flags=re.I)
        cleaned = re.sub(r"\s+", " ", cleaned).strip(" .?!:\"'")
        return cleaned if len(cleaned) >= 3 else None

    def _match_github_repos(self, items: list[dict], query: str) -> list[dict]:
        needle = query.lower()
        matches = []
        for item in items:
            haystack = " ".join(
                [
                    str(item.get("name") or ""),
                    str(item.get("full_name") or ""),
                    str(item.get("description") or ""),
                    str(item.get("language") or ""),
                    str(item.get("readme") or ""),
                ]
            ).lower()
            if needle in haystack:
                matches.append(item)
        return matches

    def _format_notion_response(self, *, message: str, normalized: str, metadata: dict, items: list[dict]) -> str:
        databases = [item for item in items if item.get("object") == "database"]
        pages = [item for item in items if item.get("object") == "page"]
        users = metadata.get("users") or []
        query = self._notion_query(message)
        matched_items = self._match_notion_items(items, query) if query else []

        if re.search(r"\b(?:task|tasks|taks|takses|todo|to-do|assigned|assignee|assignment|owner|owners)\b", normalized):
            task_response = self._format_notion_tasks_response(items=items, users=users)
            if task_response:
                return task_response

        if re.search(r"\b(?:member|members|user|users|people|person|team)\b", normalized):
            if not users:
                return "I synced Notion, but Notion did not return visible workspace members for this connection."
            lines = ["I synced Notion. These workspace users are visible:"]
            for index, user in enumerate(users[:15], start=1):
                name = user.get("name") or "Unnamed user"
                email = f" - {user.get('email')}" if user.get("email") else ""
                user_type = f" ({user.get('type')})" if user.get("type") else ""
                lines.append(f"{index}. {name}{email}{user_type}")
            return "\n".join(lines)

        if re.search(r"\b(?:list|show|what|which)\b.{0,60}\b(?:database|databases)\b", normalized):
            if not databases:
                return "I synced Notion. I could not see any databases in the recent accessible workspace items."
            lines = ["I synced Notion. These databases are visible:"]
            for index, item in enumerate(databases[:10], start=1):
                props = item.get("properties") or []
                detail = f" - properties: {', '.join(props[:6])}" if props else ""
                lines.append(f"{index}. {item.get('title') or 'Untitled'}{detail}")
            return "\n".join(lines)

        if re.search(r"\b(?:list|show|what|which)\b.{0,60}\b(?:page|pages|docs|documents)\b", normalized):
            if not pages:
                return "I synced Notion. I could not see any pages in the recent accessible workspace items."
            lines = ["I synced Notion. These pages are visible:"]
            for index, item in enumerate(pages[:10], start=1):
                edited = item.get("last_edited_time")
                lines.append(f"{index}. {item.get('title') or 'Untitled'}{f' - edited {edited}' if edited else ''}")
            return "\n".join(lines)

        if query and matched_items:
            lines = [f"I searched your visible Notion context for \"{query}\" and found:"]
            for index, item in enumerate(matched_items[:6], start=1):
                title = item.get("title") or "Untitled"
                object_type = item.get("object") or "item"
                excerpt = item.get("excerpt") or ""
                props = item.get("properties") or []
                detail = excerpt[:260] if excerpt else f"Properties: {', '.join(props[:8])}" if props else ""
                lines.append(f"{index}. {title} - {object_type}{f': {detail}' if detail else ''}")
            return "\n".join(lines)

        if re.search(r"\b(?:summarize|summary|context|what you can see|overview|workspace context)\b", normalized):
            database_titles = [item.get("title") or "Untitled" for item in databases[:6]]
            page_titles = [item.get("title") or "Untitled" for item in pages[:6]]
            excerpts = [f"{item.get('title') or 'Untitled'}: {item.get('excerpt')}" for item in pages if item.get("excerpt")]
            lines = [
                "I synced your Notion workspace and can see a lightweight workspace overview.",
                "",
                f"Connected workspace: {metadata.get('workspace_name') or 'Notion workspace'}",
                f"Visible items: {len(items)} recent items",
                f"Databases: {len(databases)}",
                f"Pages: {len(pages)}",
                f"Workspace users visible: {len(users)}",
            ]
            if database_titles:
                lines.extend(["", "Main databases I can see:"])
                lines.extend(f"- {title}" for title in database_titles)
            if page_titles:
                lines.extend(["", "Recent pages I can see:"])
                lines.extend(f"- {title}" for title in page_titles)
            if excerpts:
                lines.extend(["", "Readable page context:"])
                lines.extend(f"- {excerpt[:240]}" for excerpt in excerpts[:4])
            lines.extend(
                [
                    "",
                    "What this suggests:",
                    "- Your Notion workspace appears organized around tasks, documents, meetings, and projects.",
                    "- CEASER can use this connection to identify visible pages and databases.",
                    "- For deeper answers, ask CEASER to read or summarize a specific visible Notion page.",
                ]
            )
            return "\n".join(lines)

        if re.search(r"\b(?:read|explain|summarize)\b", normalized):
            readable_pages = [item for item in pages if item.get("excerpt")]
            if readable_pages:
                lines = ["I synced Notion and read the available page excerpts:"]
                for index, item in enumerate(readable_pages[:5], start=1):
                    lines.append(f"{index}. {item.get('title') or 'Untitled'}: {item.get('excerpt')[:420]}")
                return "\n".join(lines)
            return "I synced Notion and found visible pages, but Notion did not return readable block text for those recent pages."

        lines = ["I synced Notion. Here are the latest visible items:"]
        for index, item in enumerate(items[:8], start=1):
            title = item.get("title") or "Untitled"
            detail = item.get("object") or item.get("last_edited_time") or ""
            lines.append(f"{index}. {title}{f' - {detail}' if detail else ''}")
        return "\n".join(lines)

    def _notion_query(self, message: str) -> str | None:
        cleaned = re.sub(r"\b(?:notion|my|workspace|context|page|pages|database|databases|docs|documents|read|find|search|show|list|summarize|summary|explain|use|check|sync|what|are|is|connected|to|from|in|account|ceaser)\b", " ", message, flags=re.I)
        cleaned = re.sub(r"\s+", " ", cleaned).strip(" .?!:\"'")
        return cleaned if len(cleaned) >= 3 else None

    def _match_notion_items(self, items: list[dict], query: str) -> list[dict]:
        needle = query.lower()
        matches = []
        for item in items:
            haystack = " ".join(
                [
                    str(item.get("title") or ""),
                    str(item.get("object") or ""),
                    str(item.get("excerpt") or ""),
                    " ".join(item.get("properties") or []),
                ]
            ).lower()
            if needle in haystack:
                matches.append(item)
        return matches

    def _format_notion_tasks_response(self, *, items: list[dict], users: list[dict]) -> str | None:
        task_databases = [
            item
            for item in items
            if item.get("object") == "database"
            and re.search(r"\b(?:task|tasks|todo|to-do|assignment|assignments)\b", str(item.get("title") or ""), re.I)
        ]
        rows = []
        for database in task_databases:
            for row in database.get("rows") or []:
                if isinstance(row, dict):
                    rows.append(row)
        if not task_databases:
            rows = [
                row
                for item in items
                if item.get("object") == "database"
                for row in (item.get("rows") or [])
                if isinstance(row, dict) and self._looks_like_notion_task(row)
            ]
        if not rows and task_databases:
            database = task_databases[0]
            props = database.get("properties") or []
            detail = f" Its visible properties are: {', '.join(props[:10])}." if props else ""
            return f"I found your Notion Tasks database, but Notion did not return visible task rows for this connection.{detail}"
        if not rows:
            return "I synced Notion, but I could not see task rows in the visible workspace items. Make sure the Tasks database is shared with CEASER."

        lines = ["I synced Notion Tasks. Here are the visible task assignments:"]
        for index, row in enumerate(rows[:12], start=1):
            props = row.get("properties") if isinstance(row.get("properties"), dict) else {}
            assignees = self._notion_people_value(props)
            status = self._notion_named_value(props, ("status", "state", "stage", "progress"))
            due = self._notion_named_value(props, ("due", "deadline", "date", "target"))
            parts = [str(row.get("title") or "Untitled task")]
            if assignees:
                parts.append(f"assigned to {assignees}")
            else:
                parts.append("unassigned")
            if status:
                parts.append(f"status: {status}")
            if due:
                parts.append(f"due: {due}")
            database = row.get("database")
            if database:
                parts.append(f"database: {database}")
            lines.append(f"{index}. " + " - ".join(parts))

        if users:
            lines.extend(["", "Workspace members visible to this connection:"])
            for user in users[:8]:
                email = f" - {user.get('email')}" if user.get("email") else ""
                lines.append(f"- {user.get('name') or 'Unnamed user'}{email}")
        return "\n".join(lines)

    def _looks_like_notion_task(self, row: dict) -> bool:
        props = row.get("properties") if isinstance(row.get("properties"), dict) else {}
        haystack = " ".join([str(row.get("title") or ""), " ".join(props.keys())]).lower()
        return any(term in haystack for term in ("task", "todo", "to-do", "status", "assignee", "assigned", "owner", "due", "deadline"))

    def _notion_people_value(self, props: dict) -> str:
        people = []
        for name, value in props.items():
            if not re.search(r"\b(?:assignee|assigned|owner|person|people|member|responsible)\b", name, re.I):
                continue
            if isinstance(value, list):
                for item in value:
                    if isinstance(item, dict):
                        label = item.get("name") or item.get("email")
                        if label:
                            people.append(str(label))
                    elif isinstance(item, str):
                        people.append(item)
            elif isinstance(value, str):
                people.append(value)
        return ", ".join(dict.fromkeys(people))

    def _notion_named_value(self, props: dict, names: tuple[str, ...]) -> str | None:
        for name, value in props.items():
            lowered = name.lower()
            if any(token in lowered for token in names):
                if isinstance(value, list):
                    simple = [str(item.get("name") if isinstance(item, dict) else item) for item in value]
                    return ", ".join(item for item in simple if item)
                if isinstance(value, (str, int, float, bool)):
                    return str(value)
        return None

    def _maybe_project_members_response(self, user_id: str, message: str) -> str | None:
        normalized = message.lower()
        if "project" not in normalized or not re.search(r"\b(member|members|team|collaborator|collaborators|who is working|who are working)\b", normalized):
            return None

        projects = self.db.query(Project).filter(Project.user_id == user_id).order_by(Project.created_at.desc()).all()
        if not projects:
            return "You do not have any CEASER projects yet. Create a project first, then I can show its members."

        project = self._match_project_from_message(projects, message)
        if not project:
            names = ", ".join(item.name for item in projects[:8])
            return f"Which project should I check? Your current projects are: {names}."

        ProjectService(self.db)._ensure_owner_member(project)
        self.db.commit()
        members = (
            self.db.query(ProjectMember)
            .filter(ProjectMember.project_id == project.id, ProjectMember.status != "removed")
            .order_by(ProjectMember.created_at.asc())
            .all()
        )
        if not members:
            return f"{project.name} does not have any listed members yet."

        lines = [f"Here are the members in {project.name}:"]
        for index, member in enumerate(members, start=1):
            display = member.name or member.email
            email = f" - {member.email}" if member.name else ""
            lines.append(f"{index}. {display}{email} ({member.role}, {member.status})")
        return "\n".join(lines)

    def _match_project_from_message(self, projects: list[Project], message: str) -> Project | None:
        normalized = message.lower()
        for project in projects:
            if project.name.lower() in normalized:
                return project
        cleaned = re.sub(r"\b(?:who|are|is|the|members?|team|collaborators?|in|of|my|project|check|show|list)\b", " ", normalized)
        cleaned = re.sub(r"\s+", " ", cleaned).strip()
        if cleaned:
            for project in projects:
                project_words = set(project.name.lower().split())
                cleaned_words = set(cleaned.split())
                if project_words and len(project_words & cleaned_words) / max(len(project_words), 1) >= 0.5:
                    return project
        return projects[0] if len(projects) == 1 else None

    def _is_explicit_google_calendar_request(self, message: str) -> bool:
        calendar_reference = bool(re.search(r"\b(?:google calendar|my calendar|calendar|calender)\b", message))
        calendar_action = bool(re.search(r"\b(?:check|show|list|read|find|add|create|schedule|sync|fit)\b", message))
        personal_event_request = bool(re.search(
            r"\b(?:what|which|show|list|check)\b.{0,40}\b(?:my events|my meetings|my availability|my free time)\b|\b(?:am i|are we)\s+(?:free|available)\b|\bmy availability\b",
            message,
        ))
        return (calendar_reference and calendar_action) or personal_event_request

    def _is_explicit_google_drive_request(self, message: str) -> bool:
        drive_reference = bool(re.search(r"\b(?:google drive|my drive|drive (?:file|files|document|documents|folder|folders)|my files)\b", message))
        data_action = bool(re.search(r"\b(?:read|find|search|open|summarize|use|show|list|look up|check|retrieve|scan)\b", message))
        return drive_reference and data_action

    def _is_explicit_gmail_request(self, message: str) -> bool:
        gmail_reference = bool(re.search(r"\b(?:gmail|my inbox|my emails?|my mail)\b", message))
        data_action = bool(re.search(r"\b(?:read|find|search|show|list|check|sync)\b", message))
        return gmail_reference and data_action

    def _maybe_identity_memory_response(self, user_id: str, message: str) -> str | None:
        normalized = message.strip()
        lower = normalized.lower()
        if not re.search(
            r"\b(remember|my name is|i am your founder|i'm your founder|who am i|who i am|what is my name|what's my name|who is your founder|your founder|founder of ceaser|who founded ceaser|who owns ceaser|who owns you|version|who are you|what are you|what is ceaser|what is ceaser os|what can you do|what is your purpose|who built you|who created you|who made you|who built ceaser|who created ceaser|who made ceaser|your name)\b",
            lower,
        ):
            return None

        stored = []
        name_match = re.search(r"\bmy name is ([A-Za-z][A-Za-z0-9 ._-]+?)(?:,| and |\.|$)", normalized, flags=re.I)
        founder_match = re.search(r"\bi (?:am|'m) your founder\b|\byour founder\b", normalized, flags=re.I)
        if name_match:
            name = name_match.group(1).strip()
            stored.extend(self.memory_capture.capture(user_id=user_id, message=f"My name is {name}."))
        if founder_match:
            stored.extend(self.memory_capture.capture(user_id=user_id, message="Remember that user is CEASER founder."))

        if stored or lower.startswith("remember"):
            if not stored:
                stored.extend(self.memory_capture.capture(user_id=user_id, message=message))
            facts = []
            if name_match:
                facts.append(f"your name is {name_match.group(1).strip()}")
            if founder_match:
                facts.append("you are my founder")
            detail = " and ".join(facts) if facts else "that"
            return f"Got it. I will remember {detail}."

        memories = self.memory_retriever.retrieve_relevant_memories(user_id=user_id, query=message)
        identity_memory_text = self._identity_memory_text(user_id)
        memory_text = " ".join([identity_memory_text, *[item.get("content", "") for item in memories]])
        profile_name = self._profile_display_name(user_id)
        user_name = profile_name or self._extract_memory_value(memory_text, r"User name is ([A-Za-z][A-Za-z0-9 ._-]+)")
        is_founder = bool(re.search(r"User is CEASER founder|user is .*founder", memory_text, flags=re.I))

        if "version" in lower:
            return "I am CEASER OS v1.0.0."
        if re.search(r"\b(who are you|what are you|what is ceaser|what is ceaser os|your name)\b", lower):
            return (
                "I am CEASER OS, your personal AI operating system. I help with chat, research, memory, files, "
                "documents, agents, workflows, desktop actions, voice commands, and daily productivity."
            )
        if re.search(r"\b(what can you do|what is your purpose)\b", lower):
            return (
                "I can help you research topics, remember important context, summarize files, create documents, "
                "manage projects, work with CEASER agents, run desktop actions, answer from your account context, "
                "and support voice-first workflows."
            )
        if re.search(r"\b(who built you|who created you|who made you|who built ceaser|who created ceaser|who made ceaser|who founded ceaser|founder of ceaser|who owns ceaser|who owns you)\b", lower):
            return "I was created by Akshay Dosapati as part of the CEASER personal AI operating system."
        if re.search(r"\bwho is your founder\b|\byour founder\b", lower):
            if is_founder and user_name:
                return f"My founder is {user_name}."
            if is_founder:
                return "You are my founder."
            return "My founder is Akshay Dosapati."
        if re.search(r"\bwho am i\b|\bwho i am\b|\bwhat is my name\b|\bwhat's my name\b", lower):
            if user_name and is_founder:
                return f"You are {user_name}, my founder."
            if user_name:
                return f"Your name is {user_name}."
            return "I do not know your name yet. Tell me, for example: 'Remember, my name is Akshay.'"
        return None

    def _profile_display_name(self, user_id: str) -> str | None:
        user = self.db.query(User).filter(User.id == user_id).first()
        if not user:
            return None
        if user.profile and user.profile.display_name:
            return user.profile.display_name.strip()
        return None

    def _identity_memory_text(self, user_id: str) -> str:
        recent_memories = self.memory_retriever.get_recent_memories(user_id, limit=100)
        identity_lines = []
        for memory in recent_memories:
            content = memory.content
            if re.search(r"\b(User name is|User is CEASER founder|User is .*founder)\b", content, flags=re.I):
                identity_lines.append(content)
        return " ".join(identity_lines)

    def _extract_memory_value(self, text: str, pattern: str) -> str | None:
        match = re.search(pattern, text, flags=re.I)
        return match.group(1).strip() if match else None

    def _calendar_target_date(self, message: str) -> date:
        normalized = message.lower()
        today = date.today()
        if "tomorrow" in normalized:
            return today + timedelta(days=1)
        if "today" in normalized:
            return today

        months = {
            "january": 1, "jan": 1,
            "february": 2, "feb": 2,
            "march": 3, "mar": 3,
            "april": 4, "apr": 4,
            "may": 5,
            "june": 6, "jun": 6,
            "july": 7, "jul": 7,
            "august": 8, "aug": 8,
            "september": 9, "sep": 9, "sept": 9,
            "october": 10, "oct": 10,
            "november": 11, "nov": 11,
            "december": 12, "dec": 12,
        }
        match = re.search(r"\b(january|jan|february|feb|march|mar|april|apr|may|june|jun|july|jul|august|aug|september|sept|sep|october|oct|november|nov|december|dec)\s+(\d{1,2})(?:st|nd|rd|th)?(?:,?\s+(\d{4}))?\b", normalized)
        if match:
            year = int(match.group(3) or today.year)
            return date(year, months[match.group(1)], int(match.group(2)))

        numeric = re.search(r"\b(\d{1,2})[/-](\d{1,2})(?:[/-](\d{2,4}))?\b", normalized)
        if numeric:
            day = int(numeric.group(1))
            month = int(numeric.group(2))
            year = int(numeric.group(3) or today.year)
            if year < 100:
                year += 2000
            return date(year, month, day)
        return today

    def _filter_calendar_events(self, events: list[dict], target_date: date) -> list[dict]:
        matched = []
        for event in events:
            raw_start = event.get("start")
            if not raw_start:
                continue
            try:
                event_date = datetime.fromisoformat(raw_start.replace("Z", "+00:00")).date()
            except ValueError:
                try:
                    event_date = date.fromisoformat(raw_start[:10])
                except ValueError:
                    continue
            if event_date == target_date:
                matched.append(event)
        return matched

    def _format_calendar_time(self, value: str | None) -> str:
        if not value:
            return "All day"
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            return parsed.strftime("%I:%M %p").lstrip("0")
        except ValueError:
            return "All day"

    def _attached_documents(
        self,
        user_id: str,
        file_ids: list[str],
        *,
        include_content: bool = True,
        trace: dict[str, Any] | None = None,
    ) -> list[dict]:
        documents = []
        file_lookup_started = perf_counter()
        permission_started = perf_counter()
        for file_id in file_ids[:3]:
            file = self.files.get(file_id)
            if not file or file.user_id != user_id:
                continue
            document_payload = {
                "id": file.id,
                "name": file.name,
                "file_type": file.file_type,
                "metadata": file.extraction_metadata,
            }
            if include_content:
                document_payload["content"] = file.extracted_content[:4000]
            documents.append(document_payload)
        if trace is not None:
            trace["file_lookup_ms"] = round((perf_counter() - file_lookup_started) * 1000, 2)
            trace["permission_check_ms"] = round((perf_counter() - permission_started) * 1000, 2)
        return documents

    def _looks_like_file_summary_request(self, message: str, attached_documents: list[dict]) -> bool:
        if not attached_documents:
            return False
        normalized = message.lower()
        terms = (
            "summarize the uploaded document",
            "summarize the uploaded file",
            "summarize this document",
            "summarize this file",
            "summarize the document",
            "summarize the file",
            "uploaded document",
            "uploaded file",
            "this pdf",
            "this document",
        )
        return any(term in normalized for term in terms)

    def _get_conversation(self, conversation_id: str | None) -> Conversation | None:
        if not conversation_id:
            return None
        return self.conversations.get(conversation_id)

    def _conversation_context(self, conversation: Conversation | None) -> dict:
        if not conversation:
            return {
                "messages": [],
                "previous_research": None,
                "inferred_topic": None,
                "summary": None,
                "history_message_count": 0,
                "history_token_count": 0,
                "latest_user_message": None,
                "latest_assistant_message": None,
                "active_topic": None,
                "active_subtopic": None,
                "last_user_intent": None,
                "message_ids": [],
                "named_entities": [],
            }

        # Read full history for inexpensive topic resolution, but keep the LLM
        # payload compact. Sending every stored report/answer adds latency and
        # can make a focused follow-up drift back to an older request.
        messages = self.conversations.list_recent_messages(conversation_id=conversation.id, limit=24)
        recent_messages = messages[-12:]
        generation_messages = messages[-6:]
        older_messages = messages[:-6]
        compact_messages = []
        previous_research = None
        latest_user_message = None
        latest_assistant_message = None
        for item in reversed(recent_messages):
            metadata = item.extra_metadata
            research = metadata.get("research") if isinstance(metadata, dict) else None
            if research and not previous_research:
                previous_research = {
                    "query": research.get("query"),
                    "summary": research.get("summary"),
                    "sources": [
                        {
                            "title": source.get("title"),
                            "url": source.get("url"),
                            "snippet": source.get("snippet"),
                        }
                        for source in (research.get("sources") or [])[:6]
                    ],
                }
        for item in recent_messages:
            metadata = item.extra_metadata
            research = metadata.get("research") if isinstance(metadata, dict) else None
            # This list is chronological.  Keep overwriting so the context holds
            # the actual most recent turn rather than the oldest retained turn.
            if item.role == "assistant":
                # Continuations need the *end* of the previous response most:
                # it is where a long streamed answer may have stopped.
                latest_assistant_message = {"id": item.id, "content": item.content[-2400:]}
            if item.role == "user":
                latest_user_message = {"id": item.id, "content": item.content[:1200]}
            compact_messages.append(
                {
                    "id": item.id,
                    "role": item.role,
                    "content": item.content[:1600],
                    "research_query": research.get("query") if research else None,
                }
            )
        topic_history_messages = [{"role": item.role, "content": item.content[:1600]} for item in messages]
        history_messages = [{"role": item.role, "content": item.content[:1600]} for item in generation_messages]
        named_entities = self._extract_entities(compact_messages)
        active_topic = self._active_topic_from_messages(topic_history_messages)
        active_subtopic = self._active_subtopic_from_messages(topic_history_messages, active_topic)
        return {
            # The response pipeline receives only recent turns plus the compact
            # summary above. Topic resolution still considers the full history.
            "messages": history_messages,
            "previous_research": previous_research,
            "inferred_topic": self._infer_topic(compact_messages),
            "summary": self._summarize_messages(older_messages),
            "history_message_count": len(messages),
            "history_token_count": max(1, round(sum(len(item.get("content", "")) for item in history_messages) / 4)),
            "latest_user_message": latest_user_message,
            "latest_assistant_message": latest_assistant_message,
            "active_topic": active_topic,
            "active_subtopic": active_subtopic,
            "last_user_intent": self._last_user_intent_from_messages(history_messages, active_topic),
            "message_ids": [item.id for item in messages],
            "named_entities": named_entities,
        }

    @staticmethod
    def _lightweight_follow_up_context(follow_up_trace: dict) -> dict:
        """Avoid intent, memory, and document retrieval for ordinary continuations."""
        return {
            "intent": "conversation_follow_up",
            "output_format": "chat",
            "evidence": "",
            "source_count": 0,
            "retrieval_scope": "conversation_only",
            "retrieval_sources": ["compact_follow_up_context"],
            "intent_domain": None,
            "intent_subdomain": follow_up_trace.get("active_subtopic"),
            "_intent_ms": 0,
            "_retrieval_ms": 0,
            "_context_total_ms": 0,
            "_context_tokens": 0,
            "document_metadata_load_ms": 0,
            "file_lookup_ms": 0,
            "chunk_load_ms": 0,
            "vector_search_ms": 0,
            "keyword_search_ms": 0,
            "rerank_ms": 0,
            "context_build_ms": 0,
            "prompt_tokens": 0,
            "selected_chunks": 0,
            "cache_hit": True,
        }

    @staticmethod
    def _minimal_chat_context() -> dict:
        """Normal questions should not pay for retrieval that they do not need."""
        return {
            "intent": "general_chat",
            "output_format": "chat",
            "evidence": "",
            "source_count": 0,
            "retrieval_scope": "none",
            "retrieval_sources": ["minimal_chat_context"],
            "intent_domain": None,
            "intent_subdomain": None,
            "_intent_ms": 0,
            "_retrieval_ms": 0,
            "_context_total_ms": 0,
            "_context_tokens": 0,
            "document_metadata_load_ms": 0,
            "file_lookup_ms": 0,
            "chunk_load_ms": 0,
            "vector_search_ms": 0,
            "keyword_search_ms": 0,
            "rerank_ms": 0,
            "context_build_ms": 0,
            "prompt_tokens": 0,
            "selected_chunks": 0,
            "cache_hit": True,
        }

    @staticmethod
    def _can_use_minimal_chat_context(*, message: str, attached_documents: list[dict], file_ids: list[str], research_result: Any) -> bool:
        if attached_documents or file_ids or research_result:
            return False
        normalized = message.lower()
        memory_terms = ("remember", "memory", "my preference", "about me", "what do you know about me", "saved information")
        document_terms = ("document", "pdf", "file", "attachment", "uploaded", "knowledge base")
        return not any(term in normalized for term in memory_terms + document_terms)

    @staticmethod
    def _follow_up_generation_context(conversation_context: dict, follow_up_trace: dict) -> list[dict]:
        """Give the model only the last relevant exchange for a continuation."""
        previous_user = str(follow_up_trace.get("previous_user_message") or "").strip()
        previous_assistant = str(follow_up_trace.get("previous_assistant_excerpt") or "").strip()
        compact: list[dict] = []
        if previous_user:
            compact.append({"role": "user", "content": previous_user[:1200]})
        if previous_assistant:
            compact.append({"role": "assistant", "content": previous_assistant[-2400:]})
        return compact or list(conversation_context.get("messages") or [])[-2:]

    def _maybe_research(self, query: str, selected_agent_names: list[str]):
        _ = selected_agent_names
        return self.research_engine.research(query)

    def _should_run_heavy_pipeline(self, message: str) -> bool:
        return self._is_explicit_workflow_creation_request(message)

    def _is_explicit_workflow_creation_request(self, message: str) -> bool:
        """Chat requests never create persistent workflow runs.

        Project workflow documents are generated through the document flow and
        saved in Files. Persistent workflow runs are reserved for dedicated
        workflow endpoints, preventing ordinary chat prompts from polluting
        the workflow output with orchestration metadata.
        """
        _ = message
        return False

    def _should_run_research(self, message: str, selected_agents: list[str]) -> bool:
        normalized = message.lower()
        explicit_research = any(
            term in normalized
            for term in [
                "research", "latest", "news", "sources", "citations", "web", "internet", "online", "competitor", "market",
                "current", "currently", "today", "recent", "as of", "this week", "this month", "this year", "live update",
                "stats", "statistics", "centuries", "career stats", "records",
            ]
        )
        _ = selected_agents
        asks_for_recent_year = bool(re.search(r"\b20(?:2[5-9]|[3-9]\d)\b", normalized))
        return explicit_research or asks_for_recent_year

    def _default_stream_agents(self, message: str) -> list[str]:
        normalized = message.lower()
        if self._is_report_request(message):
            # Reports should be informed by the relevant specialties, not be
            # treated as a Friday-only content request. The final report is
            # still one coherent response from the primary LLM.
            agents = ["Nova"]
            if any(term in normalized for term in ["business", "startup", "strategy", "market", "revenue", "growth", "saas"]):
                agents.append("Zeus")
            if any(term in normalized for term in ["technical", "system", "software", "app", "platform", "ai", "robot", "robotics", "engineering", "architecture", "healthcare"]):
                agents.append("Atlas")
            if any(term in normalized for term in ["project plan", "implementation plan", "execution", "timeline", "tasks", "milestone", "deadline"]):
                agents.append("Bolt")
            if any(term in normalized for term in ["content", "marketing", "campaign", "brand", "social"]):
                agents.append("Friday")
            return list(dict.fromkeys(agents))[:3]
        if any(term in normalized for term in ["business", "startup", "strategy", "market"]):
            return ["Nova", "Zeus"]
        if any(term in normalized for term in ["research", "search", "sources", "competitor", "market research"]):
            return ["Nova"]
        if any(term in normalized for term in ["study", "learn", "exam", "notes"]):
            return ["Alex"]
        if any(term in normalized for term in ["content", "email", "post", "caption"]):
            return ["Friday"]
        return ["Alex"]

    @staticmethod
    def _is_report_request(message: str) -> bool:
        normalized = message.lower()
        return bool(re.search(r"\b(?:report|project plan|implementation plan|system design)\b", normalized))

    @staticmethod
    def _requires_rich_context(message: str) -> bool:
        """Keep only genuinely contextual requests on the retrieval path."""
        normalized = message.lower()
        return any(
            term in normalized
            for term in ("startup", "business", "strategy", "project plan", "report", "workflow", "market", "competitor")
        )

    def _research_query(self, message: str, conversation_context: dict | None = None) -> str:
        normalized = message.strip()
        previous_research = (conversation_context or {}).get("previous_research") or {}
        previous_query = (previous_research.get("query") or "").strip()
        inferred_topic = ((conversation_context or {}).get("inferred_topic") or "").strip()
        carryover_topic = previous_query or inferred_topic
        if carryover_topic and self._is_follow_up_research_request(normalized):
            return self._follow_up_research_query(normalized, carryover_topic)

        quoted = re.findall(r'"([^"]+)"|' + r"'([^']+)'", normalized)
        quoted_terms = [first or second for first, second in quoted if first or second]
        if quoted_terms:
            return quoted_terms[0].strip()

        if self._is_current_statistics_request(normalized):
            return self._current_statistics_query(normalized)

        topic_patterns = [
            r"\bresearch\s+(?:on|about)?\s*(.+?)(?:\s+and\s+(?:give|show|share|list)|\s+then\s+(?:give|show|share|list)|$)",
            r"\bdo\s+(?:some\s+)?research\s+(?:on|about)?\s*(.+?)(?:\s+and\s+(?:give|show|share|list)|\s+then\s+(?:give|show|share|list)|$)",
            r"\bsearch\s+(?:the\s+web\s+)?(?:for|about)?\s*(.+?)(?:\s+and\s+(?:give|show|share|list)|\s+then\s+(?:give|show|share|list)|$)",
            r"\blook\s+up\s+(.+?)(?:\s+and\s+(?:give|show|share|list)|\s+then\s+(?:give|show|share|list)|$)",
            r"\bcheck\s+(.+?)\s+(?:on|in|using)\s+(?:the\s+)?(?:web|internet|online)\b",
        ]
        for pattern in topic_patterns:
            match = re.search(pattern, normalized, flags=re.I)
            if match:
                cleaned = self._clean_research_query(match.group(1))
                if cleaned:
                    return cleaned

        name_match = re.search(r"\b(?:name|called)\s+([A-Z][A-Za-z0-9_-]{2,})\b", normalized)
        if name_match:
            return name_match.group(1)

        proper_names = re.findall(r"\b[A-Z][A-Za-z0-9_-]{4,}\b", normalized)
        blocked = {"CEASER", "Nova", "Atlas", "Zeus", "Alex", "Friday", "Bolt"}
        proper_names = [name for name in proper_names if name not in blocked]
        if proper_names:
            return proper_names[0]

        cleaned = re.sub(r"\b(do|some|research|on|about|and|then|give|me|the|resources|you|did|search|web|using|name|check|please)\b", " ", normalized, flags=re.I)
        cleaned = self._clean_research_query(cleaned)
        return cleaned or normalized

    def _clean_research_query(self, value: str) -> str:
        cleaned = re.sub(r"\b(a|an|the|and|then|me|please|resources|sources|links|citations|you|did|found|for|this|topic)\b", " ", value, flags=re.I)
        cleaned = re.sub(r"\s+", " ", cleaned).strip(" .?,")
        return cleaned

    def _is_current_statistics_request(self, message: str) -> bool:
        normalized = message.lower()
        has_freshness = any(term in normalized for term in ["current", "latest", "as of", "today", "updated", "recent"])
        has_stats = any(term in normalized for term in ["stats", "statistics", "centuries", "runs", "records", "career"])
        return has_freshness and has_stats

    def _current_statistics_query(self, message: str) -> str:
        cleaned = self._clean_research_query(message)
        if not re.search(r"\b(?:2026|latest|current|updated)\b", cleaned, flags=re.I):
            cleaned = f"{cleaned} latest 2026"
        if not re.search(r"\b(?:official|espncricinfo|icc|stats)\b", cleaned, flags=re.I):
            cleaned = f"{cleaned} official stats"
        return cleaned

    def _is_follow_up_research_request(self, message: str) -> bool:
        normalized = message.lower()
        follow_up_terms = [
            "top",
            "list",
            "these",
            "those",
            "them",
            "from that",
            "from this",
            "just give",
            "give me",
            "make a list",
        ]
        has_follow_up = any(term in normalized for term in follow_up_terms)
        has_new_topic = any(term in normalized for term in ["healthtech", "healthcare", "digital health", "medtech", "biotech", "2026", "2025"])
        return has_follow_up and not has_new_topic

    def _follow_up_research_query(self, message: str, previous_query: str) -> str:
        count_match = re.search(r"\btop\s+(\d+)\b", message, flags=re.I)
        count = count_match.group(1) if count_match else ""
        prefix = f"top {count} " if count else ""
        if "startups" in previous_query.lower() or "startup" in previous_query.lower():
            return f"{prefix}{previous_query}".strip()
        return f"{prefix}startups from {previous_query}".strip()

    def _contextualize_follow_up(self, message: str, follow_up_trace: dict) -> str:
        if not follow_up_trace.get("follow_up_detected"):
            return message
        topic = (follow_up_trace.get("active_topic") or "").strip()
        if not topic:
            return message
        previous_user = (follow_up_trace.get("previous_user_message") or "").strip()
        previous_assistant = (follow_up_trace.get("previous_assistant_excerpt") or "").strip()
        summary = (follow_up_trace.get("conversation_summary") or "").strip()
        entities = ", ".join(follow_up_trace.get("resolved_entities") or [])
        intent = follow_up_trace.get("follow_up_intent") or "expand"
        subtopic = (follow_up_trace.get("active_subtopic") or "").strip()
        instruction_by_intent = {
            "continue": "Continue from the last useful point. Do not repeat the answer already given.",
            "simplify": "Explain the active topic in simpler language while keeping the topic unchanged.",
            "summarize": "Give a concise summary of the active topic and the prior answer.",
            "examples": "Give concrete examples that clarify the active topic.",
            "history": "Answer the history aspect of the active topic.",
            "why_how": "Answer the user's why/how question about the active topic.",
            "subtopic": "Treat this as a subtopic of the active topic. Keep the main topic and focus on this specific part.",
            "expand": "Expand the prior answer with new, useful detail; do not define the wording of the follow-up in isolation.",
        }
        return "\n\n".join(
            [
                "System instruction: Resolve the current request using the active conversation topic. Do not treat vague words such as 'depth', 'detail', 'more', 'continue', 'it', or 'this' as independent topics. Do not describe CEASER unless explicitly asked.",
                f"Active topic: {topic}",
                f"Active subtopic: {subtopic or 'None'}",
                f"Follow-up intent: {intent}",
                instruction_by_intent.get(intent, instruction_by_intent["expand"]),
                f"Resolved entities: {entities or topic}",
                f"Previous user message: {previous_user or 'None'}",
                f"Previous assistant answer: {previous_assistant or 'None'}",
                f"Older conversation summary: {summary or 'None'}",
                f"Current user message: {message}",
            ]
        )

    def _follow_up_trace(self, *, message: str, conversation_context: dict, parent_message_id: str | None) -> dict:
        previous_research = conversation_context.get("previous_research") or {}
        latest_assistant_message = conversation_context.get("latest_assistant_message") or {}
        latest_user_message = conversation_context.get("latest_user_message") or {}
        latest_assistant_content = latest_assistant_message.get("content", "") if isinstance(latest_assistant_message, dict) else ""
        latest_user_content = latest_user_message.get("content", "") if isinstance(latest_user_message, dict) else ""
        prior_topic = (
            conversation_context.get("active_topic")
            or previous_research.get("query")
            or conversation_context.get("inferred_topic")
            or self._topic_from_previous_assistant(latest_assistant_content)
            or self._topic_from_previous_user(latest_user_content)
        )
        prior_subtopic = conversation_context.get("active_subtopic")
        resolution = self._resolve_conversation_turn(message, prior_topic, prior_subtopic)
        active_topic = resolution.get("active_topic") or prior_topic
        active_subtopic = resolution.get("active_subtopic") or prior_subtopic
        # A clearly introduced subject becomes the new active topic.  A vague
        # request stays attached to the existing one.
        if resolution.get("new_topic"):
            active_topic = resolution.get("explicit_topic") or active_topic
            active_subtopic = None
        if not active_topic:
            active_topic = (
            previous_research.get("query")
            or conversation_context.get("inferred_topic")
            or self._topic_from_previous_assistant(latest_assistant_content)
            or self._topic_from_previous_user(latest_user_content)
            )
        follow_up_detected = bool(resolution.get("follow_up_detected") and active_topic)
        resolved_entities = list(conversation_context.get("named_entities") or [])
        if active_topic and active_topic not in resolved_entities:
            resolved_entities.insert(0, active_topic)
        context_source = []
        if latest_user_content:
            context_source.append("previous_user_message")
        if latest_assistant_content:
            context_source.append("previous_assistant_answer")
        if conversation_context.get("summary"):
            context_source.append("conversation_summary")
        if parent_message_id:
            context_source.append("parent_message_id")
        return {
            "follow_up_detected": follow_up_detected,
            "follow_up_intent": resolution.get("intent"),
            "active_topic": active_topic,
            "active_subtopic": active_subtopic,
            "resolved_entities": resolved_entities[:6],
            "context_source": context_source,
            "previous_user_message": latest_user_content,
            "previous_assistant_excerpt": latest_assistant_content,
            "conversation_summary": conversation_context.get("summary"),
        }

    def _is_conversation_follow_up(self, message: str) -> bool:
        return bool(self._resolve_conversation_turn(message, None).get("follow_up_detected"))

    def _resolve_conversation_turn(self, message: str, prior_topic: str | None, prior_subtopic: str | None = None) -> dict:
        """Classify a turn before generating an answer.

        Short requests are deliberately resolved against the active topic.  This
        prevents phrases such as "explain in depth" from becoming a request to
        explain the word "depth".
        """
        normalized = re.sub(r"\s+", " ", message.lower()).strip(" .?!")
        explicit_subtopic = self._extract_subtopic_request(message, prior_topic)
        explicit_topic = self._extract_explicit_topic(message)
        follow_up_patterns = {
            "continue": r"^(continue|go on|keep going|carry on|what else)(?:\s+please)?$|\bcontinue (?:from|with)\b|\b(?:response|answer|generation|it)\s+(?:stopped|was cut off|cut off|ended)\b|\b(?:finish|complete)\s+(?:it|the response|the answer)\b",
            "simplify": r"\b(explain|say|put).{0,20}\b(simple|simpler|plain)\b|\bin simple words\b|\bbriefly\b|\bshort version\b",
            "summarize": r"\b(summarize|summary|recap|tl;dr)\b",
            "examples": r"\b(example|examples|illustrate|use case|use cases)\b",
            "history": r"\b(history|historical|origin|origins|background)\b",
            "why_how": r"^(why|how)(\s|$)|\b(why|how) (does|do|did|is|are|can|would)\b",
            "expand": r"\b(?:explain(?: me)?|tell me|give me|go) (?:more|further|deeper|depth|detail|in depth|in detail|in detail please)\b|\b(elaborate|more details|more information|everything about)\b|^(more|details|depth|detail|in depth|in detail)$",
        }
        intent = next((name for name, pattern in follow_up_patterns.items() if re.search(pattern, normalized)), None)
        # A request to resume a cut-off answer is a continuation even though
        # the generic topic extractor can turn its wording into a faux topic.
        if intent == "continue":
            explicit_topic = None
        pronoun_reference = bool(re.search(r"\b(this|that|it|them|they|him|her|the previous answer|above)\b", normalized))
        connector = bool(re.match(r"^(and|also|then|so)\b", normalized))
        is_short = len(normalized.split()) <= 7
        vague_follow_up = bool(intent or pronoun_reference or connector)

        if explicit_subtopic and prior_topic:
            return {
                "follow_up_detected": True,
                "new_topic": False,
                "explicit_topic": None,
                "active_topic": prior_topic,
                "active_subtopic": explicit_subtopic,
                "intent": "subtopic",
            }

        # A named subject is a new topic even if the wording also contains a
        # follow-up phrase (for example, "tell me more about Bahubali").  The
        # generic follow-up filter above has already removed phrases such as
        # "explain in depth" and "tell me more", which should stay attached
        # to the active topic.
        if explicit_topic:
            return {
                "follow_up_detected": False,
                "new_topic": True,
                "explicit_topic": explicit_topic,
                "active_topic": explicit_topic,
                "active_subtopic": None,
                "intent": "new_topic",
            }
        return {
            "follow_up_detected": vague_follow_up,
            "new_topic": False,
            "explicit_topic": None,
            "active_topic": prior_topic,
            "active_subtopic": prior_subtopic,
            "intent": intent or "expand",
        }

    def _extract_subtopic_request(self, message: str, prior_topic: str | None) -> str | None:
        if not prior_topic:
            return None
        normalized = re.sub(r"\s+", " ", message).strip(" .?!")
        history_match = re.search(r"\b(?:its|the)\s+(history|culture|geography|economy|tourism|architecture|food|education|transportation)\b", normalized, flags=re.I)
        if history_match:
            return history_match.group(1).title()
        about_match = re.fullmatch(r"(?:what|how) about (?:the )?(.+)", normalized, flags=re.I)
        if about_match:
            candidate = about_match.group(1).strip(" .?!")
            if candidate and len(candidate.split()) <= 8:
                return candidate.title()
        generic_subtopics = {
            "history", "culture", "tourism", "geography", "economy", "architecture",
            "food", "education", "transportation", "festivals", "rulers", "dynasty",
            "wodeyars", "wodeyar",
        }
        topic_match = re.fullmatch(
            r"(?:now\s+)?(?:explain|tell me about|describe)\s+(?:the\s+)?(.+)",
            normalized,
            flags=re.I,
        )
        if topic_match:
            candidate = topic_match.group(1).strip(" .?!").lower()
            if candidate in generic_subtopics:
                return candidate.title()
        return None

    def _extract_explicit_topic(self, message: str) -> str | None:
        value = re.sub(r"\s+", " ", message).strip(" .?!")
        if not value or self._is_generic_follow_up_phrase(value):
            return None
        value = re.sub(
            r"^(?:now\s+)?(?:can you\s+)?(?:please\s+)?(?:tell|explain|describe|teach|show|give|help me understand|what is|what are)\s+(?:me\s+)?(?:more\s+)?(?:about\s+)?",
            "",
            value,
            flags=re.I,
        )
        value = re.sub(r"^(?:about\s+)", "", value, flags=re.I)
        value = re.sub(r"\b(?:please|in detail|in depth|briefly|more|further)\b", " ", value, flags=re.I)
        value = re.sub(r"\s+", " ", value).strip(" .?!")
        if not value or self._is_generic_follow_up_phrase(value):
            return None
        return value[:160]

    def _is_generic_follow_up_phrase(self, value: str) -> bool:
        normalized = re.sub(r"\s+", " ", value.lower()).strip(" .?!")
        return bool(re.fullmatch(
            r"(?:explain(?: me)?(?: in)?|tell me|give me|go)?\s*(?:more|more details|more information|depth|detail|in depth|in detail|briefly|continue|go deeper|elaborate|examples?|why|how|what else|everything|this|that|it|them|they|the previous answer)",
            normalized,
        ))

    def _active_topic_from_messages(self, messages: list[dict]) -> str | None:
        """Replay user turns so topic changes and subtopics stay distinct."""
        active_topic = None
        active_subtopic = None
        for item in messages:
            if item.get("role") != "user":
                continue
            resolution = self._resolve_conversation_turn(item.get("content", ""), active_topic, active_subtopic)
            if resolution.get("new_topic"):
                active_topic = resolution.get("active_topic")
                active_subtopic = None
            elif resolution.get("active_topic"):
                active_topic = resolution.get("active_topic")
                active_subtopic = resolution.get("active_subtopic") or active_subtopic
        return active_topic

    def _active_subtopic_from_messages(self, messages: list[dict], topic: str | None) -> str | None:
        active_topic = None
        active_subtopic = None
        for item in messages:
            if item.get("role") != "user":
                continue
            resolution = self._resolve_conversation_turn(item.get("content", ""), active_topic, active_subtopic)
            if resolution.get("new_topic"):
                active_topic = resolution.get("active_topic")
                active_subtopic = None
            elif resolution.get("active_topic"):
                active_topic = resolution.get("active_topic")
                active_subtopic = resolution.get("active_subtopic") or active_subtopic
        return active_subtopic if active_topic == topic else None

    def _last_user_intent_from_messages(self, messages: list[dict], topic: str | None) -> str | None:
        subtopic = self._active_subtopic_from_messages(messages, topic)
        for item in reversed(messages):
            if item.get("role") == "user":
                return self._resolve_conversation_turn(item.get("content", ""), topic, subtopic).get("intent")
        return None

    def _summarize_messages(self, messages: list) -> str | None:
        if not messages:
            return None
        snippets: list[str] = []
        for item in messages[-8:]:
            content = item.content.strip()
            if not content:
                continue
            snippets.append(f"{item.role}: {content[:180]}")
        return " | ".join(snippets)[:900] if snippets else None

    def _extract_entities(self, messages: list[dict]) -> list[str]:
        combined = " ".join(item.get("content", "") for item in messages)
        title_case = re.findall(r"\b[A-Z][a-zA-Z]{2,}(?:\s+[A-Z][a-zA-Z]{2,})?\b", combined)
        ignored = {"Ceaser", "System", "Current", "User", "Assistant", "Important", "None"}
        entities: list[str] = []
        for item in title_case:
            cleaned = item.strip()
            if cleaned in ignored or cleaned in entities:
                continue
            entities.append(cleaned)
        return entities[:8]

    def _topic_from_previous_assistant(self, content: str) -> str | None:
        match = re.search(r"\*\*(.+?)\*\*", content)
        if match:
            return match.group(1).split(":")[0].strip()
        return None

    def _topic_from_previous_user(self, content: str) -> str | None:
        return self._extract_explicit_topic(content)

    def _infer_topic(self, messages: list[dict]) -> str | None:
        text = " ".join(item.get("content", "") for item in messages).lower()
        if "healthtech" in text and "startup" in text and "2026" in text:
            return "healthtech startups started in 2026"
        if "healthcare" in text and "startup" in text and "2026" in text:
            return "healthcare startups started in 2026"
        if "digital health" in text and "startup" in text and "2026" in text:
            return "digital health startups started in 2026"
        return None
