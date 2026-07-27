from __future__ import annotations

from collections.abc import AsyncIterator
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
            return generate_text_sync(instructions=instructions, input_text=context_text)
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
        documents = self._document_context(intent=intent, documents=context.get("documents", []))
        if intent == "file_summary":
            evidence = knowledge_context.get("evidence", "")
            context_text = "\n\n".join(
                [
                    f"User request:\n{message}",
                    f"File metadata:\n{documents}",
                    f"Document evidence:\n{evidence}",
                ]
            )
            instructions = (
                "You are CEASER document intelligence. Summarize the uploaded file using the document evidence below. "
                "Treat the evidence as the file content extracted from CEASER. "
                "Do not say the content is unavailable when evidence exists. "
                "Write a direct summary with key ideas and a short takeaway."
            )
            return instructions, context_text
        instructions = (
            "You are CEASER, a personal AI operating system. Answer the user's request directly. "
            "Use the provided CEASER context, memories, research, files, and project details when relevant. "
            "Choose the response format that matches the task. Do not force every answer into Executive Summary, Key Trends, and Recommendations. "
            "Do not mention internal orchestration, selected agents, or framework names unless the user asks. "
            "If document knowledge evidence is present, summarize or answer from that evidence directly and do not claim the document content is unavailable. "
            f"{detail_policy}"
        )
        context_text = "\n\n".join(
                [
                    f"User request:\n{message}",
                    f"Memories:\n{context.get('memories', [])}",
                    f"Conversation:\n{context.get('conversation', [])}",
                    f"Documents:\n{documents}",
                    f"Knowledge evidence:\n{knowledge_context.get('evidence', '')}",
                    f"Research:\n{context.get('research_result')}",
                    f"Agent context:\n{context.get('merged_contributions', {})}",
                ]
            )
        return instructions, context_text

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
