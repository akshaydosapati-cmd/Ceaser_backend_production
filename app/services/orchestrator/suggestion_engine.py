from __future__ import annotations

import re
from dataclasses import dataclass

from app.intelligence.orchestrator.models import IntentType


GENERIC_SUGGESTIONS = [
    "Summarize this",
    "Explain in more detail",
    "Compare with another topic",
]


@dataclass(frozen=True, slots=True)
class SuggestionItem:
    text: str
    action_type: str
    category: str
    confidence: float


class SuggestionEngine:
    def generate(
        self,
        *,
        user_query: str,
        response_text: str,
        intent: str | None,
        retrieval_scope: str | None,
        output_format: str | None,
        conversation_context: dict | None,
        recent_suggestions: list[str] | None = None,
        max_items: int = 5,
    ) -> list[SuggestionItem]:
        category = self._detect_category(
            user_query=user_query,
            response_text=response_text,
            intent=intent,
            retrieval_scope=retrieval_scope,
            output_format=output_format,
        )
        generated = self._category_suggestions(
            category=category,
            user_query=user_query,
            response_text=response_text,
            intent=intent,
            retrieval_scope=retrieval_scope,
            output_format=output_format,
            conversation_context=conversation_context or {},
        )
        filtered = self._dedupe_and_filter(
            generated,
            recent_suggestions=recent_suggestions or [],
            max_items=max_items,
        )
        if filtered:
            return filtered
        return self._fallback(category=category, max_items=min(3, max_items))

    def _detect_category(
        self,
        *,
        user_query: str,
        response_text: str,
        intent: str | None,
        retrieval_scope: str | None,
        output_format: str | None,
    ) -> str:
        text = f"{user_query}\n{response_text}".lower()
        normalized_intent = (intent or "").lower()
        normalized_scope = (retrieval_scope or "").lower()
        normalized_format = (output_format or "").lower()

        if any(token in text for token in ["study", "exam", "revision", "flashcard", "mcq", "notes", "chapter", "syllabus"]):
            return "education"
        if any(token in text for token in ["python", "javascript", "react", "api", "bug", "code", "debug", "algorithm", "sql"]):
            return "programming"
        if any(token in text for token in ["startup", "business", "market", "competitor", "pitch", "revenue", "gtm", "sales"]):
            return "business"
        if any(token in text for token in ["write", "essay", "caption", "draft", "email", "blog", "linkedin", "cover letter"]):
            return "writing"
        if any(token in text for token in ["research", "source", "citation", "latest", "report", "analysis", "findings"]):
            return "research"
        if any(token in text for token in ["schedule", "task", "calendar", "plan my day", "todo", "workflow", "productivity"]):
            return "productivity"
        if any(token in text for token in ["finance", "stock", "budget", "investment", "profit", "cash flow", "pricing"]):
            return "finance"
        if any(token in text for token in ["health", "fitness", "diet", "medical", "symptom", "wellness", "sleep"]):
            return "health"
        if any(token in text for token in ["mythology", "epic", "history", "story", "character", "philosophy", "lesson"]):
            return "education"

        if normalized_intent in {IntentType.FILE_SUMMARY.value, IntentType.FILE_LOOKUP.value}:
            return "research"
        if normalized_intent in {IntentType.EMAIL_DRAFT.value, IntentType.EMAIL_SEND.value}:
            return "writing"
        if normalized_intent in {IntentType.CALENDAR_LOOKUP.value, IntentType.CALENDAR_CREATE.value, IntentType.WORKFLOW.value}:
            return "productivity"
        if normalized_intent == IntentType.DOCUMENT_GENERATION.value:
            return "writing" if normalized_format in {"document", "email"} else "business"
        if normalized_scope == "web":
            return "research"
        return "general"

    def _category_suggestions(
        self,
        *,
        category: str,
        user_query: str,
        response_text: str,
        intent: str | None,
        retrieval_scope: str | None,
        output_format: str | None,
        conversation_context: dict,
    ) -> list[SuggestionItem]:
        text = f"{user_query}\n{response_text}".lower()
        normalized_intent = (intent or "").lower()
        previous_topic = (conversation_context.get("inferred_topic") or "").strip()
        topic = self._extract_topic(user_query, response_text)
        study_mode = self._is_study_workflow(text)
        story_mode = self._is_story_or_character_query(user_query, response_text)
        comparison_mode = self._is_comparison_query(user_query, response_text)
        table_mode = self._is_table_like_response(response_text)
        suggestions: list[SuggestionItem] = []

        def add(text_value: str, action_type: str, confidence: float = 0.86) -> None:
            suggestions.append(
                SuggestionItem(
                    text=self._shorten(text_value),
                    action_type=action_type,
                    category=category,
                    confidence=confidence,
                )
            )

        if category == "education":
            if study_mode:
                add("Create revision questions", "generate_questions")
                add("Make a study timetable", "create_timetable")
                add("Turn this into flashcards", "generate_flashcards")
                if "compare" not in text:
                    add("Compare related concepts", "compare_topics", 0.78)
            else:
                add("Explain this more simply", "simplify")
                add("List the key lessons", "extract_lessons")
                add("Generate quiz questions", "generate_questions")
                if not comparison_mode:
                    add("Compare related concepts", "compare_topics", 0.78)
                if story_mode:
                    add("List the key traits", "character_traits", 0.81)

        elif category == "programming":
            add("Show working code example", "generate_code")
            add("Explain the bug cause", "debug_explanation")
            add("Refactor this cleanly", "refactor_code")
            add("Write test cases", "generate_tests", 0.81)

        elif category == "business":
            add("Build an action plan", "create_plan")
            add("Generate investor questions", "generate_questions")
            add("Compare competitors", "compare_topics")
            if any(token in text for token in ["pitch", "deck", "presentation"]):
                add("Turn this into slides", "create_pitch")
            else:
                add("Export as PDF", "export_pdf", 0.76)

        elif category == "writing":
            add("Rewrite professionally", "rewrite")
            add("Make it more concise", "shorten")
            add("Add a stronger opening", "improve_hook", 0.8)
            if any(token in text for token in ["email", "mail", "subject"]):
                add("Turn into follow-up email", "follow_up_email")

        elif category == "research":
            add("Compare with another topic", "compare_topics")
            add("Turn this into report", "create_report")
            add("Extract key findings", "extract_findings")
            if normalized_intent == IntentType.FILE_SUMMARY.value:
                add("List document action items", "extract_actions")
            elif retrieval_scope == "web":
                add("Show trusted sources only", "filter_sources", 0.79)

        elif category == "productivity":
            add("Turn this into checklist", "create_checklist")
            add("Add this to calendar", "calendar_create")
            add("Break into next steps", "next_steps")
            add("Create weekly plan", "weekly_plan", 0.79)

        elif category == "finance":
            add("Turn this into budget", "create_budget")
            add("Compare best options", "compare_options")
            add("List financial risks", "risk_review")
            add("Convert this into table", "create_table", 0.78)

        elif category == "health":
            add("Summarize key precautions", "summarize_precautions")
            add("Create healthy routine", "create_routine")
            add("Compare treatment options", "compare_options")
            add("List warning signs", "extract_warnings", 0.78)

        else:
            if topic:
                add(f"Explain {topic} simply", "simplify", 0.72)
                add(f"Give {topic} examples", "examples", 0.7)
                if not comparison_mode:
                    add(f"Compare {topic} broadly", "compare_topics", 0.69)
            add("Explain in more detail", "expand", 0.68)
            add("Compare with another topic", "compare_topics", 0.68)
            if story_mode:
                add("List the key traits", "character_traits", 0.76)

        if previous_topic and previous_topic.lower() not in text and category in {"research", "business", "education"}:
            add(f"Relate this to {previous_topic}", "relate_topic", 0.72)

        if table_mode or any(token in text for token in ["table", "timetable", "plan", "schedule"]):
            add("Convert this into chart", "create_chart", 0.73)
        if any(token in text for token in ["interview", "questions", "prepare"]):
            add("Generate interview questions", "generate_questions", 0.84)
        if any(token in text for token in ["document", "pdf", "report", "proposal"]):
            add("Export as PDF", "export_pdf", 0.77)
        if story_mode:
            add("Summarize the main story", "story_summary", 0.78)
            add("Explain the life lessons", "practical_lessons", 0.83)
        if comparison_mode:
            add("List the main differences", "compare_topics", 0.79)

        return suggestions

    def _dedupe_and_filter(
        self,
        suggestions: list[SuggestionItem],
        *,
        recent_suggestions: list[str],
        max_items: int,
    ) -> list[SuggestionItem]:
        recent_normalized = {self._normalize(item) for item in recent_suggestions}
        results: list[SuggestionItem] = []
        seen: set[str] = set()
        for suggestion in suggestions:
            normalized = self._normalize(suggestion.text)
            if normalized in seen or normalized in recent_normalized:
                continue
            if not self._looks_relevant(suggestion.text):
                continue
            seen.add(normalized)
            results.append(suggestion)
            if len(results) >= max_items:
                break
        return results

    def _fallback(self, *, category: str, max_items: int) -> list[SuggestionItem]:
        fallback_pool = [
            "Summarize this",
            "Explain in more detail",
            "Compare with another topic",
            "Give a practical example",
            "Turn this into checklist",
        ]
        return [
            SuggestionItem(text=item, action_type="generic_follow_up", category=category, confidence=0.56)
            for item in fallback_pool[:max_items]
        ]

    def _looks_relevant(self, text: str) -> bool:
        cleaned = text.strip()
        if not cleaned:
            return False
        return len(cleaned.split()) <= 8 or len(cleaned) <= 48

    def _shorten(self, text: str) -> str:
        cleaned = re.sub(r"\s+", " ", text.strip())
        if len(cleaned) <= 48:
            return cleaned
        shortened = cleaned[:45].rstrip(" ,.;:")
        return f"{shortened}..."

    def _normalize(self, text: str) -> str:
        return re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()

    def _is_study_workflow(self, text: str) -> bool:
        return any(token in text for token in ["study", "exam", "revision", "flashcard", "mcq", "syllabus", "timetable"])

    def _is_story_or_character_query(self, user_query: str, response_text: str) -> bool:
        combined = f"{user_query}\n{response_text}".lower()
        return any(
            token in combined
            for token in ["story", "character", "traits", "who is", "tell me about", "explain about", "life lessons", "mythology", "epic"]
        )

    def _is_comparison_query(self, user_query: str, response_text: str) -> bool:
        combined = f"{user_query}\n{response_text}".lower()
        return any(token in combined for token in ["compare", "difference", "vs ", "versus"])

    def _is_table_like_response(self, response_text: str) -> bool:
        lowered = response_text.lower()
        return "|" in response_text or any(token in lowered for token in ["day |", "phase |", "week |", "time |"])

    def _extract_topic(self, user_query: str, response_text: str) -> str | None:
        query = re.sub(r"[^a-zA-Z0-9\s-]", " ", user_query).strip()
        lowered = query.lower()
        lowered = re.sub(
            r"\b(explain|tell|about|give|create|write|make|help|prepare|show|describe|generate|please|can|you|just|me)\b",
            " ",
            lowered,
        )
        lowered = re.sub(r"\s+", " ", lowered).strip(" -")
        if lowered:
            words = [word for word in lowered.split() if len(word) > 2][:4]
            if words:
                return " ".join(words)

        first_heading = re.search(r"^\s{0,3}#+?\s+([A-Za-z0-9][^\n]{2,50})", response_text, flags=re.MULTILINE)
        if first_heading:
            return first_heading.group(1).strip()
        return None
