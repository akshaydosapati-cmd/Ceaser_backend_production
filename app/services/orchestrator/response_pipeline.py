from __future__ import annotations

from collections.abc import AsyncIterator
import json
from time import perf_counter
from typing import Any

from app.intelligence.ai.sync import generate_text_sync, stream_text
from app.services.llm.provider import LLMProvider


class ResponsePipeline:
    def __init__(self, provider: LLMProvider | None = None):
        self.provider = provider

    def generate(self, message: str, context: dict) -> str:
        instructions, context_text = self._build_prompt(message=message, context=context)
        try:
            response = generate_text_sync(instructions=instructions, input_text=context_text)
            return self.normalize_structured_response(response) if self.requires_structured_response(context) else response
        except Exception:
            if self.provider:
                return self.provider.generate_response(message=message, context=context)
            return "AI service is temporarily unavailable. Please try again later."

    async def stream(self, message: str, context: dict, *, trace: dict[str, Any] | None = None) -> AsyncIterator[str]:
        prompt_started = perf_counter()
        instructions, context_text = self._build_prompt(message=message, context=context)
        if trace is not None:
            trace["context_tokens"] = self._estimate_tokens(f"{instructions}\n\n{context_text}")
            trace["prompt_tokens"] = trace["context_tokens"]
            trace["prompt_build_ms"] = round((perf_counter() - prompt_started) * 1000, 2)
        async for chunk in stream_text(instructions=instructions, input_text=context_text, trace=trace):
            yield chunk

    def _build_prompt(self, *, message: str, context: dict) -> tuple[str, str]:
        detail_policy = self._detail_policy(message)
        knowledge_context = context.get("knowledge_context", {}) or {}
        intent = (knowledge_context.get("intent") or "").lower()
        retrieval_scope = (knowledge_context.get("retrieval_scope") or "").lower()
        documents = self._document_context(intent=intent, documents=context.get("documents", []))
        memories = context.get("memories", []) or []
        conversation = context.get("conversation", []) or []
        conversation_history = self._format_conversation_history(conversation)
        conversation_summary = context.get("conversation_summary") or "None"
        follow_up_trace = context.get("follow_up_trace", {}) or {}
        active_topic = follow_up_trace.get("active_topic") or "None"
        active_subtopic = follow_up_trace.get("active_subtopic") or "None"
        continuity_context = "\n".join(
            [
                f"Active topic: {active_topic}",
                f"Active subtopic: {active_subtopic}",
                f"Conversation history (chronological):\n{conversation_history or 'None'}",
                f"Older conversation summary: {conversation_summary}",
            ]
        )
        research = context.get("research_result")
        merged_contributions = context.get("merged_contributions", {}) or {}
        selected_agents = merged_contributions.get("selected_agents", []) if isinstance(merged_contributions, dict) else []
        friday_rule = self._friday_presentation_rule(message) if "Friday" in selected_agents else ""
        streaming_rule = "" if friday_rule else self._streaming_presentation_rule()
        speed_rule = self._speed_first_rule()
        evidence = knowledge_context.get("evidence", "")
        freshness_rule = (
            "When live research is provided, treat its sources as the authority for present-day facts. "
            "Do not replace them with model memory; if no reliable live source exists, say so briefly rather than guessing. "
            if research else ""
        )

        if intent == "file_summary":
            context_text = "\n\n".join(
                [
                    f"User request:\n{message}",
                    continuity_context,
                    f"File metadata:\n{documents}",
                    f"Document evidence:\n{evidence}",
                ]
            )
            instructions = (
                f"{self._tool_routing_rule()} "
                "You are CEASER document intelligence. Summarize the uploaded file using the document evidence below. "
                "Treat the evidence as the file content extracted from CEASER. "
                "Do not say the content is unavailable when evidence exists. "
                "Write a direct summary with key ideas and a short takeaway."
            )
            return instructions, context_text

        if retrieval_scope == "none" and not documents and not memories and not evidence and not research:
            instructions = (
                f"{self._tool_routing_rule()} "
                "You are CEASER, a context-persistent personal AI operating system. Answer using the chronological conversation history below, "
                "not the final user message in isolation. Continue the active topic/subtopic unless the user clearly introduces a new topic. "
                "When the user names a different subject, answer that subject directly as the first part of the answer; never scold them for changing topics, discuss conversation management, or ask them to get back on track. "
                f"{freshness_rule}"
                f"{friday_rule}"
                f"{streaming_rule}"
                f"{speed_rule}"
                "Choose the response format that best matches the request. "
                f"{detail_policy}"
            )
            return instructions, "\n\n".join([f"User request:\n{message}", continuity_context])

        if retrieval_scope == "conversation_only" and conversation and not documents and not memories and not evidence:
            instructions = (
                f"{self._tool_routing_rule()} "
                "You are CEASER, a context-persistent personal AI operating system. Continue the conversation naturally using the chronological chat history below. "
                "If the user names a different subject, switch to it and answer directly. Do not repeat yourself, discuss conversation management, scold the user for changing topics, or ask them to get back on track. "
                f"{freshness_rule}"
                f"{friday_rule}"
                f"{streaming_rule}"
                f"{speed_rule}"
                f"{detail_policy}"
            )
            return instructions, "\n\n".join([f"User request:\n{message}", continuity_context])

        instructions = (
            f"{self._tool_routing_rule()} "
            "You are CEASER, a context-persistent personal AI operating system. Answer the user's request using the chronological conversation history and active topic below. "
            "Do not process the latest request in isolation; continue the active topic/subtopic unless a new topic is explicit. "
            "A clearly named different subject is a new topic: answer it directly and never comment that the conversation has strayed, started over, or needs to get back on track. "
            "Use the provided CEASER context, memories, research, files, and project details when relevant. "
            "Choose the response format that matches the task. Do not force every answer into Executive Summary, Key Trends, and Recommendations. "
            "Do not mention internal orchestration, selected agents, or framework names unless the user asks. "
            "If document knowledge evidence is present, summarize or answer from that evidence directly and do not claim the document content is unavailable. "
            f"{freshness_rule}"
            f"{friday_rule}"
            f"{streaming_rule}"
            f"{speed_rule}"
            f"{detail_policy}"
        )
        context_text = "\n\n".join(
                [
                    f"User request:\n{message}",
                    continuity_context,
                    f"Memories:\n{memories}",
                    f"Documents:\n{documents}",
                    f"Knowledge evidence:\n{evidence}",
                    f"Research:\n{research}",
                    f"Agent context:\n{merged_contributions}",
                ]
            )
        return instructions, context_text

    @staticmethod
    def _friday_presentation_rule(message: str) -> str:
        """Friday returns data that CEASER can validate and render as UI."""
        _ = message
        return (
            " You are Friday, CEASER's Business Strategy Agent. Your response is consumed by the CEASER frontend. "
            "Return valid JSON only. Do not include Markdown, headings, prose before or after the JSON, Markdown tables, or decorative explanations. "
            "Always return this exact top-level shape: "
            '{"type":"answer|project|research|strategy|plan|document_analysis|business_analysis|task_plan|comparison|workflow|report",'
            '"title":"short title","summary":"2-4 sentence summary","sections":[{"title":"string","description":"string","items":[]}],'
            '"actions":[],"next_steps":[],"warnings":[]}. '
            "Use only sections relevant to the request. Split information into meaningful sections rather than placing a report in one item. "
            "For tasks use objects with task, description, priority, status, owner, and dependency. For phases use phase, name, objective, tasks, deliverable, and status. "
            "For risks use risk, impact, mitigation, and status. Use 'Not specified' for unknown values. Never invent dates, costs, names, owners, specifications, results, status, requirements, or technical details. "
            "Keep next_steps actionable and put missing information, unverified assumptions, and required confirmation in warnings."
        )

    @staticmethod
    def _streaming_presentation_rule() -> str:
        return (
            " Your response is displayed while it streams, so write it exactly in its final polished form from the first token. "
            "Start directly with the answer—never expose planning, internal reasoning, or filler. Use valid Markdown only: headings must use '# ' or '## ' and have a blank line after them; each bullet or numbered item must be on its own line; separate paragraphs with blank lines. "
            "Do not concatenate bold labels with text or lists, do not create malformed Markdown, and use a table only after its complete structure is known. "
            "For a follow-up, answer the active topic directly without repeating the entire previous answer."
        )

    @staticmethod
    def _speed_first_rule() -> str:
        return (
            " Speed is a priority: begin useful output immediately and aim to complete ordinary requests in about five seconds when no external tool, large document, or heavy workflow is required. "
            "Answer simple questions immediately. For normal requests, give the direct answer first and then only relevant supporting detail. "
            "Do not over-plan, repeat the user request, overgenerate, or create a long report unless explicitly requested. Use external research or integrations only when genuinely required. "
            "For follow-ups, answer only the requested part of the active topic. Never expose internal reasoning."
        )

    @staticmethod
    def requires_structured_response(context: dict) -> bool:
        merged = context.get("merged_contributions", {}) if isinstance(context, dict) else {}
        selected_agents = merged.get("selected_agents", []) if isinstance(merged, dict) else []
        return "Friday" in selected_agents

    @staticmethod
    def normalize_structured_response(response: str) -> str:
        """Validate Friday output so persisted and completed stream payloads are always usable JSON."""
        candidate = response.strip()
        if candidate.startswith("```"):
            candidate = candidate.split("\n", 1)[1] if "\n" in candidate else ""
            candidate = candidate.rsplit("```", 1)[0].strip()
        try:
            payload = json.loads(candidate)
        except (TypeError, ValueError):
            payload = None

        if not isinstance(payload, dict):
            return json.dumps({
                "type": "answer",
                "title": "Structured response unavailable",
                "summary": "Friday returned a response that could not be validated as structured data.",
                "sections": [],
                "actions": [],
                "next_steps": ["Regenerate the response."],
                "warnings": ["The generated response was not valid JSON."],
            }, ensure_ascii=False)

        allowed_types = {"answer", "project", "research", "strategy", "plan", "document_analysis", "business_analysis", "task_plan", "comparison", "workflow", "report"}
        response_type = payload.get("type") if payload.get("type") in allowed_types else "answer"

        def text(value: Any, fallback: str = "") -> str:
            return value.strip() if isinstance(value, str) and value.strip() else fallback

        def items(value: Any) -> list[Any]:
            return [item for item in value if isinstance(item, (str, int, float, bool, dict))] if isinstance(value, list) else []

        sections: list[dict[str, Any]] = []
        for section in payload.get("sections", []):
            if not isinstance(section, dict):
                continue
            sections.append({
                "title": text(section.get("title"), "Untitled section"),
                "description": text(section.get("description")),
                "items": items(section.get("items")),
            })

        normalized = {
            "type": response_type,
            "title": text(payload.get("title"), "Friday response"),
            "summary": text(payload.get("summary"), "No summary was provided."),
            "sections": sections,
            "actions": items(payload.get("actions")),
            "next_steps": items(payload.get("next_steps")),
            "warnings": items(payload.get("warnings")),
        }
        return json.dumps(normalized, ensure_ascii=False)

    def _format_conversation_history(self, conversation: list[dict]) -> str:
        """Preserve the speaker roles so an LLM can resolve follow-up turns."""
        lines: list[str] = []
        for turn in conversation:
            role = str(turn.get("role", "user")).strip().lower()
            label = "Assistant" if role == "assistant" else "User"
            content = str(turn.get("content", "")).strip()
            if content:
                lines.append(f"{label}: {content}")
        return "\n".join(lines)

    def _tool_routing_rule(self) -> str:
        return (
            "CRITICAL TOOL ROUTING RULE: Integrations are optional. Never assume Google Calendar, Google Drive, Gmail, "
            "or another integration is required because a request mentions a plan, schedule, meeting, file, email, or recommendation. "
            "Use an integration only when the user explicitly asks to access or act on that integration. "
            "For itineraries, trip plans, meeting suggestions, explanations, recommendations, summaries, and follow-ups, answer directly. "
            "A disconnected integration must never replace an answer that can be given normally."
            " For factual requests, do not invent names, cast members, dates, plot details, citations, or statistics. State uncertainty briefly when needed instead of guessing."
        )

    def _detail_policy(self, message: str) -> str:
        normalized = message.lower()
        if any(term in normalized for term in ["study plan", "timetable", "time table", "schedule for study"]):
            return "Return a clear study timetable table with days/times/topics/tasks. Avoid generic business sections."
        if any(term in normalized for term in ["email", "mail", "gmail", "cover letter"]):
            return "Return an email-ready draft with subject and body. Include only useful send/edit next actions."
        if any(term in normalized for term in ["summarize the uploaded document", "summarize the uploaded file", "summarize this document", "summarize this file", "summarize the document", "summarize the file"]):
            return "Return a direct summary of the document evidence with the main ideas, key points, and concise takeaway. Do not say the content is unavailable when evidence is present."
        if any(term in normalized for term in ["document", "pdf", "report", "business plan", "pitch deck", "proposal"]):
            return "Return document-style content with real section content, not placeholder instructions."
        if any(term in normalized for term in ["research", "latest", "news", "market", "competitor"]):
            return "Return a structured research answer with findings, evidence, uncertainty, and sources if available."
        if any(term in normalized for term in ["explain", "what is", "how does", "compare", "difference"]):
            return "Return a detailed but easy-to-understand explanation with headings, bullets, examples, and final summary."
        return "Use concise or standard detail based on the request."

    def _estimate_tokens(self, text: str) -> int:
        return max(1, round(len(text) / 4))

    def _document_context(self, *, intent: str, documents: list[dict]) -> list[dict]:
        if intent != "file_summary":
            return documents
        compact: list[dict] = []
        for document in documents[:3]:
            compact.append(
                {
                    "id": document.get("id"),
                    "name": document.get("name"),
                    "file_type": document.get("file_type"),
                    "metadata": document.get("metadata"),
                }
            )
        return compact
