from __future__ import annotations

import re
from datetime import date, datetime, timedelta

from sqlalchemy.orm import Session

from app.agents.registry import AgentRegistry
from app.engines.research_engine import ResearchEngine
from app.models.conversation import Conversation
from app.models.user import User
from app.repositories.file_repository import FileRepository
from app.services.conversation_service import ConversationService
from app.services.orchestrator.context_builder import ContextBuilder
from app.services.orchestrator.memory_capture import MemoryCapture
from app.services.orchestrator.memory_retriever import MemoryRetriever
from app.services.orchestrator.response_pipeline import ResponsePipeline
from app.services.orchestrator.user_context_resolver import UserContextResolver
from app.services.workflows import WorkflowOrchestrator
from app.services.integrations import IntegrationManager


class CeaserOrchestrator:
    def __init__(self, db: Session):
        self.db = db
        self.user_context_resolver = UserContextResolver(db)
        self.memory_retriever = MemoryRetriever(db)
        self.agent_registry = AgentRegistry()
        self.context_builder = ContextBuilder(db)
        self.memory_capture = MemoryCapture(db)
        self.conversations = ConversationService(db)
        self.research_engine = ResearchEngine()
        self.files = FileRepository(db)
        self.workflow_orchestrator = WorkflowOrchestrator(db)
        self.response_pipeline = ResponsePipeline()

    def handle_message(self, user_id: str, message: str, conversation_id: str | None = None, file_ids: list[str] | None = None) -> dict:
        attached_documents = self._attached_documents(user_id=user_id, file_ids=file_ids or [])
        effective_message = message
        if attached_documents:
            names = ", ".join(document["name"] for document in attached_documents)
            effective_message = f"{message}\n\nAttached document(s): {names}"

        conversation = self._get_conversation(conversation_id)
        conversation_context = self._conversation_context(conversation)
        effective_message = self._contextualize_follow_up(effective_message, conversation_context)
        if conversation:
            self.conversations.create_message(
                conversation_id=conversation.id,
                role="user",
                content=message,
                metadata={"attached_files": [{"id": item["id"], "name": item["name"], "file_type": item["file_type"]} for item in attached_documents]},
            )
            if conversation.title == "New Chat":
                self.conversations.rename(conversation, self.conversations.generate_title(message))

        calendar_response = self._maybe_calendar_response(user_id=user_id, message=effective_message)
        if calendar_response:
            return self._direct_response(
                user_id=user_id,
                conversation=conversation,
                conversation_id=conversation_id,
                conversation_context=conversation_context,
                response=calendar_response,
                selected_agents=["Alex"],
                workflow_type="calendar_lookup",
                summary="Calendar lookup completed.",
            )

        identity_memory_response = self._maybe_identity_memory_response(user_id=user_id, message=message)
        if identity_memory_response:
            return self._direct_response(
                user_id=user_id,
                conversation=conversation,
                conversation_id=conversation_id,
                conversation_context=conversation_context,
                response=identity_memory_response,
                selected_agents=["Alex"],
                workflow_type="memory_identity",
                summary="Identity memory updated.",
            )

        workflow = self.workflow_orchestrator.run(user_id=user_id, message=effective_message, conversation_id=conversation_id, file_ids=file_ids or [])
        selected_agent_names = workflow.selected_agents
        research_query = self._research_query(message, conversation_context)
        research_result = self._maybe_research(query=research_query, selected_agent_names=selected_agent_names)
        memories = self.memory_retriever.retrieve_relevant_memories(user_id=user_id, query=effective_message)
        captured_memories = self.memory_capture.capture(user_id=user_id, message=message)
        final_response = self.response_pipeline.generate(
            message=effective_message,
            context={
                "scope": {"name": "CEASER", "type": "personal_ai_os"},
                "current_message": effective_message,
                "memories": memories,
                "conversation": conversation_context["messages"],
                "previous_research": conversation_context["previous_research"],
                "projects": [],
                "documents": attached_documents,
                "merged_contributions": {
                    "selected_agents": selected_agent_names,
                    "contributions": workflow.contributions,
                    "summary": workflow.result_summary,
                    "workflow_response": workflow.final_response,
                },
                "research_result": research_result.model_dump() if research_result else None,
            },
        )
        captured_response_memories = self.memory_capture.capture_interaction(
            user_id=user_id,
            user_message=message,
            assistant_response=final_response,
        )
        response_payload = {
            "scope": "personal_ai_os",
            "conversation_id": conversation.id if conversation else conversation_id,
            "selected_agents": selected_agent_names,
            "contributions": workflow.contributions,
            "contribution_summary": workflow.result_summary,
            "memories_used": memories,
            "research": research_result.model_dump() if research_result else None,
            "workflow": {
                "id": workflow.workflow_id,
                "type": workflow.workflow_type,
                "status": workflow.status,
                "steps": workflow.steps,
                "summary": workflow.result_summary,
            },
            "context_summary": {
                "user_id": user_id,
                "scope_name": "CEASER",
                "memory_count": len(memories),
                "project_count": 0,
                "conversation_message_count": len(conversation_context["messages"]),
                "enabled_agent_count": len(selected_agent_names),
                "captured_memory_count": len(captured_memories) + len(captured_response_memories),
                "attached_document_count": len(attached_documents),
                "workflow_id": workflow.workflow_id,
            },
            "response": final_response,
        }
        if conversation:
            self.conversations.create_message(
                conversation_id=conversation.id,
                role="assistant",
                content=final_response,
                metadata={key: value for key, value in response_payload.items() if key not in {"conversation_id", "response"}},
            )
        return response_payload

    def _direct_response(
        self,
        user_id: str,
        conversation: Conversation | None,
        conversation_id: str | None,
        conversation_context: dict,
        response: str,
        selected_agents: list[str],
        workflow_type: str,
        summary: str,
    ) -> dict:
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
            },
            "response": response,
        }
        if conversation:
            self.conversations.create_message(
                conversation_id=conversation.id,
                role="assistant",
                content=response,
                metadata={key: value for key, value in response_payload.items() if key not in {"conversation_id", "response"}},
            )
        return response_payload

    def _maybe_calendar_response(self, user_id: str, message: str) -> str | None:
        normalized = message.lower()
        if not re.search(r"\b(calendar|calender|event|events|schedule|meeting|meetings)\b", normalized):
            return None

        target_date = self._calendar_target_date(message)
        try:
            metadata = IntegrationManager(self.db).metadata(user_id=user_id, provider_id="google-calendar")
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

    def _attached_documents(self, user_id: str, file_ids: list[str]) -> list[dict]:
        documents = []
        for file_id in file_ids[:3]:
            file = self.files.get(file_id)
            if not file or file.user_id != user_id:
                continue
            documents.append({"id": file.id, "name": file.name, "file_type": file.file_type, "metadata": file.extraction_metadata, "content": file.extracted_content[:20000]})
        return documents

    def _get_conversation(self, conversation_id: str | None) -> Conversation | None:
        if not conversation_id:
            return None
        return self.conversations.get(conversation_id)

    def _conversation_context(self, conversation: Conversation | None) -> dict:
        if not conversation:
            return {"messages": [], "previous_research": None, "inferred_topic": None}

        messages = self.conversations.list_messages(conversation_id=conversation.id, limit=100)
        recent_messages = messages[-8:]
        compact_messages = []
        previous_research = None
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
            compact_messages.append(
                {
                    "role": item.role,
                    "content": item.content[:1600],
                    "research_query": research.get("query") if research else None,
                }
            )
        return {"messages": compact_messages, "previous_research": previous_research, "inferred_topic": self._infer_topic(compact_messages)}

    def _maybe_research(self, query: str, selected_agent_names: list[str]):
        if "Nova" not in selected_agent_names:
            return None
        return self.research_engine.research(query)

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

    def _contextualize_follow_up(self, message: str, conversation_context: dict) -> str:
        if not self._is_follow_up_research_request(message):
            return message
        previous_research = conversation_context.get("previous_research") or {}
        topic = (previous_research.get("query") or conversation_context.get("inferred_topic") or "").strip()
        if not topic:
            return message
        return (
            f"{message}\n\n"
            f"Important conversation context: this is a follow-up to the previous topic '{topic}'. "
            f"Answer within that topic. If the user asks for top startups, provide startup/company names, not startup categories."
        )

    def _infer_topic(self, messages: list[dict]) -> str | None:
        text = " ".join(item.get("content", "") for item in messages).lower()
        if "healthtech" in text and "startup" in text and "2026" in text:
            return "healthtech startups started in 2026"
        if "healthcare" in text and "startup" in text and "2026" in text:
            return "healthcare startups started in 2026"
        if "digital health" in text and "startup" in text and "2026" in text:
            return "digital health startups started in 2026"
        return None
