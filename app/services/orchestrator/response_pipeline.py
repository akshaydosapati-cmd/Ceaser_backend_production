from __future__ import annotations

from app.intelligence.ai.sync import generate_text_sync
from app.services.llm.provider import LLMProvider


class ResponsePipeline:
    def __init__(self, provider: LLMProvider | None = None):
        self.provider = provider

    def generate(self, message: str, context: dict) -> str:
        detail_policy = self._detail_policy(message)
        instructions = (
            "You are CEASER, a personal AI operating system. Answer the user's request directly. "
            "Use the provided CEASER context, memories, research, files, and project details when relevant. "
            "Choose the response format that matches the task. Do not force every answer into Executive Summary, Key Trends, and Recommendations. "
            "Do not mention internal orchestration, selected agents, or framework names unless the user asks. "
            f"{detail_policy}"
        )
        context_text = "\n\n".join(
            [
                f"User request:\n{message}",
                f"Memories:\n{context.get('memories', [])}",
                f"Conversation:\n{context.get('conversation', [])}",
                f"Documents:\n{context.get('documents', [])}",
                f"Knowledge evidence:\n{context.get('knowledge_context', {}).get('evidence', '')}",
                f"Research:\n{context.get('research_result')}",
                f"Agent context:\n{context.get('merged_contributions', {})}",
            ]
        )
        try:
            return generate_text_sync(instructions=instructions, input_text=context_text)
        except Exception:
            if self.provider:
                return self.provider.generate_response(message=message, context=context)
            return "AI service is temporarily unavailable. Please try again later."

    def _detail_policy(self, message: str) -> str:
        normalized = message.lower()
        if any(term in normalized for term in ["study plan", "timetable", "time table", "schedule for study"]):
            return "Return a clear study timetable table with days/times/topics/tasks. Avoid generic business sections."
        if any(term in normalized for term in ["email", "mail", "gmail", "cover letter"]):
            return "Return an email-ready draft with subject and body. Include only useful send/edit next actions."
        if any(term in normalized for term in ["document", "pdf", "report", "business plan", "pitch deck", "proposal"]):
            return "Return document-style content with real section content, not placeholder instructions."
        if any(term in normalized for term in ["research", "latest", "news", "market", "competitor"]):
            return "Return a structured research answer with findings, evidence, uncertainty, and sources if available."
        if any(term in normalized for term in ["explain", "what is", "how does", "compare", "difference"]):
            return "Return a detailed but easy-to-understand explanation with headings, bullets, examples, and final summary."
        return "Use concise or standard detail based on the request."
