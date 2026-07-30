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
            return self.normalize_structured_response(response, project_report=self._is_project_report_context(context)) if self.requires_structured_response(context) else response
        except Exception:
            if self.provider:
                return self.provider.generate_response(message=message, context=context)
            return "AI service is temporarily unavailable. Please try again later."

    async def stream(self, message: str, context: dict, *, trace: dict[str, Any] | None = None) -> AsyncIterator[str]:
        prompt_started = perf_counter()
        instructions, context_text = self._build_prompt(message=message, context=context)
        output_budget = self._stream_output_budget(message=message, context=context)
        if trace is not None:
            trace["context_tokens"] = self._estimate_tokens(f"{instructions}\n\n{context_text}")
            trace["prompt_tokens"] = trace["context_tokens"]
            trace["prompt_build_ms"] = round((perf_counter() - prompt_started) * 1000, 2)
            trace["max_output_tokens"] = output_budget
        async for chunk in stream_text(instructions=instructions, input_text=context_text, max_output_tokens=output_budget, trace=trace):
            yield chunk

    @staticmethod
    def _stream_output_budget(*, message: str, context: dict) -> int:
        """Reserve only the completion budget needed for the current request."""
        normalized = message.lower()
        selected = (context.get("merged_contributions", {}) or {}).get("selected_agents", []) if isinstance(context, dict) else []
        if "Friday" in selected or any(term in normalized for term in ("report", "document", "project plan", "workflow", "proposal")):
            return 1600
        if any(term in normalized for term in ("in depth", "detailed", "more details", "go deeper", "elaborate", "comprehensive", "implementation details", "complete explanation")):
            return 1300
        greetings = {"hello", "hi", "hey", "hello ceaser", "hi ceaser", "thanks", "thank you"}
        if normalized.strip(" .!?") in greetings:
            return 180
        return 750

    def _build_prompt(self, *, message: str, context: dict) -> tuple[str, str]:
        current_request = str(context.get("latest_user_message") or message).strip()
        detail_policy = self._detail_policy(current_request)
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
        report_rule = self._project_report_presentation_rule() if self._is_project_report_context(context) else ""
        friday_rule = self._friday_presentation_rule(current_request) if "Friday" in selected_agents and not report_rule else ""
        streaming_rule = "" if (friday_rule or report_rule) else self._streaming_presentation_rule()
        speed_rule = self._speed_first_rule()
        fidelity_rule = self._instruction_fidelity_rule()
        continuation_rule = self._continuation_rule(context.get("follow_up_trace", {}))
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
                f"{report_rule}"
                f"{friday_rule}"
                f"{streaming_rule}"
                f"{speed_rule}"
                f"{fidelity_rule}"
                f"{continuation_rule}"
                "Choose the response format that best matches the request. "
                f"{detail_policy}"
            )
            return instructions, "\n\n".join([f"Current user request:\n{current_request}", continuity_context])

        if retrieval_scope == "conversation_only" and conversation and not documents and not memories and not evidence:
            instructions = (
                f"{self._tool_routing_rule()} "
                "You are CEASER, a context-persistent personal AI operating system. Continue the conversation naturally using the chronological chat history below. "
                "If the user names a different subject, switch to it and answer directly. Do not repeat yourself, discuss conversation management, scold the user for changing topics, or ask them to get back on track. "
                f"{freshness_rule}"
                f"{report_rule}"
                f"{friday_rule}"
                f"{streaming_rule}"
                f"{speed_rule}"
                f"{fidelity_rule}"
                f"{continuation_rule}"
                f"{detail_policy}"
            )
            return instructions, "\n\n".join([f"Current user request:\n{current_request}", continuity_context])

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
            f"{report_rule}"
            f"{friday_rule}"
            f"{streaming_rule}"
            f"{speed_rule}"
            f"{fidelity_rule}"
            f"{continuation_rule}"
            f"{detail_policy}"
        )
        context_text = "\n\n".join(
                [
                    f"Current user request:\n{current_request}",
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
    def _project_report_presentation_rule() -> str:
        return (
            " Return valid JSON only for a polished CEASER project report. Do not include Markdown, code fences, or text outside the JSON. "
            'Use this exact top-level shape: {"type":"project_report","title":"string","executive_summary":"string",'
            '"objective":[],"context":"string","key_requirements":{"functional":[],"non_functional":[]},'
            '"scope":{"in_scope":[],"out_of_scope":[]},"proposed_solution":"string","system_workflow":[],'
            '"components":{},"implementation":[],"tasks":[],"timeline":[],"testing":[],"risks":[],'
            '"expected_outcome":"string","next_steps":[]}. '
            "Use only applicable fields, but keep the keys with an empty string, object, or list when information is unavailable. "
            "Implementation entries must contain phase, objective, tasks, deliverable, owner, dependencies, and status. "
            "Risk entries must contain risk, impact, and mitigation. Never invent dates, budgets, owners, performance claims, sources, or technical facts; state 'Not specified' where needed."
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
            " Speed is a priority for response start: begin useful output immediately and stream continuously. Do not wait for a complete answer before sending the first useful content. "
            "Fast start does not mean a short answer. Answer simple questions immediately; for normal requests, give the direct answer first and then relevant supporting detail. "
            "Do not over-plan, repeat the user request or conversation history, overgenerate, or create a long report unless explicitly requested. Use external research, retrieval, document processing, or integrations only when genuinely required. "
            "When the user requests details, depth, implementation detail, a comprehensive explanation, or a full report, provide substantial useful content without padding or repetition. For follow-ups, answer only the requested part of the active topic. Never expose internal reasoning."
        )

    @staticmethod
    def _instruction_fidelity_rule() -> str:
        return (
            " CRITICAL USER INSTRUCTION FIDELITY: Answer exactly what the latest user request asks. The latest clear request overrides older user requests; use conversation history only to resolve references and preserve the active topic, subtopic, terminology, facts, and requested format. "
            "Do not reinterpret a focused request as a full report, project overview, or unrelated expansion. A request for implementation details means implementation details only; a request for a block diagram means a block diagram only; a request to explain hardware means hardware only. "
            "Answer every requested part, preserve the user's specific terms and numbers, and do not add unsolicited content. Never invent dates, costs, names, owners, specifications, results, status, or requirements. Use 'Not specified' when information is missing. Ask one concise clarification only when the request is genuinely ambiguous and a wrong choice would matter."
        )

    @staticmethod
    def _continuation_rule(follow_up_trace: dict[str, Any]) -> str:
        if not isinstance(follow_up_trace, dict) or not follow_up_trace.get("follow_up_detected"):
            return ""
        topic = str(follow_up_trace.get("active_topic") or "the active topic")
        subtopic = str(follow_up_trace.get("active_subtopic") or "").strip()
        focus = f" Focus on the active subtopic '{subtopic}'." if subtopic else ""
        return (
            f" This is a lightweight continuation of '{topic}'.{focus} Add new, relevant information only; do not regenerate the previous answer, restart from an introduction, or repeat prior headings, paragraphs, facts, or examples unless needed for clarity. "
            "Use the compact previous exchange supplied in the context, skip unrelated material, and begin the continuation immediately. For open-ended requests such as 'more details', provide substantial new detail; for 'in depth', 'detailed', or 'go deeper', provide a significantly deeper continuation (roughly 800–1500 words when the topic supports it) unless the user asks for a different length."
        )

    @staticmethod
    def requires_structured_response(context: dict) -> bool:
        if ResponsePipeline._is_project_report_context(context):
            return True
        merged = context.get("merged_contributions", {}) if isinstance(context, dict) else {}
        selected_agents = merged.get("selected_agents", []) if isinstance(merged, dict) else []
        return "Friday" in selected_agents

    @staticmethod
    def _is_project_report_context(context: dict) -> bool:
        return isinstance(context, dict) and bool(context.get("report_request"))

    @staticmethod
    def normalize_structured_response(response: str, *, project_report: bool = False) -> str:
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
            if project_report:
                return json.dumps(ResponsePipeline._normalize_project_report({}), ensure_ascii=False)
            return json.dumps({
                "type": "answer",
                "title": "Structured response unavailable",
                "summary": "Friday returned a response that could not be validated as structured data.",
                "sections": [],
                "actions": [],
                "next_steps": ["Regenerate the response."],
                "warnings": ["The generated response was not valid JSON."],
            }, ensure_ascii=False)

        if project_report or payload.get("type") == "project_report":
            return json.dumps(ResponsePipeline._normalize_project_report(payload), ensure_ascii=False)

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

    @staticmethod
    def _normalize_project_report(payload: dict[str, Any]) -> dict[str, Any]:
        def text(value: Any, fallback: str = "") -> str:
            return value.strip() if isinstance(value, str) and value.strip() else fallback

        def items(value: Any) -> list[Any]:
            return [item for item in value if isinstance(item, (str, int, float, bool, dict))] if isinstance(value, list) else []

        requirements = payload.get("key_requirements") if isinstance(payload.get("key_requirements"), dict) else {}
        scope = payload.get("scope") if isinstance(payload.get("scope"), dict) else {}
        components = payload.get("components") if isinstance(payload.get("components"), dict) else {}
        return {
            "type": "project_report",
            "title": text(payload.get("title"), "Project Report"),
            "executive_summary": text(payload.get("executive_summary")),
            "objective": items(payload.get("objective")),
            "context": text(payload.get("context")),
            "key_requirements": {"functional": items(requirements.get("functional")), "non_functional": items(requirements.get("non_functional"))},
            "scope": {"in_scope": items(scope.get("in_scope")), "out_of_scope": items(scope.get("out_of_scope"))},
            "proposed_solution": text(payload.get("proposed_solution")),
            "system_workflow": items(payload.get("system_workflow")),
            "components": components,
            "implementation": items(payload.get("implementation")),
            "tasks": items(payload.get("tasks")),
            "timeline": items(payload.get("timeline")),
            "testing": items(payload.get("testing")),
            "risks": items(payload.get("risks")),
            "expected_outcome": text(payload.get("expected_outcome")),
            "next_steps": items(payload.get("next_steps")),
        }

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
