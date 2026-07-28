from __future__ import annotations

import json
import re
from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Any

from app.intelligence.ai.errors import AIServiceUnavailableError
from app.intelligence.ai.sync import generate_text_sync
from app.intelligence.orchestrator.models import IntentType


AVAILABLE_FEATURES = {
    "charts",
    "tables",
    "timeline",
    "pdf",
    "workflow",
    "email",
    "calendar",
    "research",
    "code",
    "projects",
}

ACTION_VERBS = {
    "add",
    "analyze",
    "build",
    "calculate",
    "compare",
    "create",
    "debug",
    "draft",
    "estimate",
    "explain",
    "export",
    "extract",
    "find",
    "generate",
    "list",
    "outline",
    "plan",
    "rewrite",
    "shorten",
    "show",
    "summarize",
    "turn",
    "visualize",
    "write",
}

BANNED_PREFIXES = (
    "can ceaser",
    "can you",
    "would you like",
    "how is",
    "tell me more",
    "learn more",
    "continue exploring",
    "ask another question",
    "more details",
)

INTENT_FALLBACKS = {
    "technology": [
        ("Compare pricing models", "compare"),
        ("Compare core services", "compare_alternatives"),
        ("Build a comparison table", "create_table"),
        ("Recommend by use case", "research"),
        ("Compare AI services", "compare"),
    ],
    "creative": [
        ("Generate logo concepts", "create_outline"),
        ("Choose a color palette", "add_examples"),
        ("Create typography ideas", "rewrite"),
        ("Design brand guidelines", "create_table"),
        ("Refine the visual style", "rewrite"),
    ],
    "career": [
        ("Create model answers", "create_outline"),
        ("Run a mock interview", "step_by_step"),
        ("Generate technical round", "generate_questions"),
        ("Generate HR questions", "generate_questions"),
        ("Create evaluation rubric", "compare"),
    ],
    "education": [
        ("Summarize key ideas", "summarize"),
        ("Create quiz questions", "generate_questions"),
        ("Compare related concepts", "compare"),
        ("Build a timeline", "create_timeline"),
        ("Explain with examples", "examples"),
    ],
    "programming": [
        ("Show a code example", "code_example"),
        ("Write test cases", "generate_tests"),
        ("Explain step by step", "step_by_step"),
        ("Compare alternatives", "compare"),
        ("Debug the implementation", "debug"),
    ],
    "business": [
        ("Build an action plan", "action_plan"),
        ("Compare competitors", "compare_competitors"),
        ("Create a pitch outline", "pitch_outline"),
        ("Estimate key metrics", "estimate_metrics"),
        ("Export as a report", "export_report"),
    ],
    "finance": [
        ("Create a budget table", "budget_table"),
        ("Show a pie chart", "create_chart"),
        ("Compare spending categories", "compare_categories"),
        ("Calculate percentages", "calculate"),
        ("Build a monthly plan", "monthly_plan"),
    ],
    "taxation": [
        ("Compare GST types", "compare"),
        ("Show a calculation example", "calculate"),
        ("Explain GST registration", "summarize"),
        ("List filing steps", "list"),
        ("Outline compliance basics", "create_outline"),
    ],
    "research": [
        ("Extract key findings", "extract_findings"),
        ("Compare reliable sources", "compare_sources"),
        ("Build a timeline", "create_timeline"),
        ("Create a summary table", "summary_table"),
        ("Generate research questions", "research_questions"),
    ],
    "travel": [
        ("Build an itinerary", "itinerary"),
        ("Estimate the budget", "estimate_budget"),
        ("Compare destinations", "compare_destinations"),
        ("List travel requirements", "travel_requirements"),
        ("Find the best season", "best_season"),
    ],
    "writing": [
        ("Create an outline", "create_outline"),
        ("Rewrite professionally", "rewrite"),
        ("Shorten the content", "shorten"),
        ("Add key examples", "add_examples"),
        ("Turn into slides", "turn_into_slides"),
    ],
    "general": [
        ("Summarize key points", "summarize"),
        ("Explain with examples", "examples"),
        ("Compare related ideas", "compare"),
    ],
}


@dataclass(frozen=True, slots=True)
class SuggestionItem:
    text: str
    action_type: str
    category: str
    confidence: float


class SuggestionEngine:
    def __init__(self) -> None:
        self.last_trace: dict[str, Any] = {}

    def generate(
        self,
        *,
        user_query: str,
        response_text: str,
        intent: str | None,
        retrieval_scope: str | None,
        output_format: str | None,
        conversation_context: dict | None,
        intent_domain: str | None = None,
        intent_subdomain: str | None = None,
        recent_suggestions: list[str] | None = None,
        max_items: int = 5,
    ) -> list[SuggestionItem]:
        recent = recent_suggestions or []
        context = conversation_context or {}
        category = self._detect_category(
            user_query=user_query,
            response_text=response_text,
            intent=intent,
            retrieval_scope=retrieval_scope,
            output_format=output_format,
            intent_domain=intent_domain,
            intent_subdomain=intent_subdomain,
        )
        generated, provider_error_category = self._generate_with_ai(
            category=category,
            user_query=user_query,
            response_text=response_text,
            intent=intent,
            retrieval_scope=retrieval_scope,
            output_format=output_format,
            intent_domain=intent_domain,
            intent_subdomain=intent_subdomain,
            conversation_context=context,
            max_items=max_items,
        )
        filtered, rejected = self._validate_suggestions(
            generated,
            user_query=user_query,
            response_text=response_text,
            category=category,
            recent_suggestions=recent,
            max_items=max_items,
        )
        if filtered:
            self.last_trace = {
                "suggestion_source": "ai" if len(filtered) == len(generated) else "filtered_ai",
                "provider_error_category": provider_error_category,
                "suggestions_before_filter": [item.text for item in generated],
                "suggestions_after_filter": [item.text for item in filtered],
                "rejected_reasons": rejected,
            }
            return filtered

        fallback = self._intent_fallback(
            category=category,
            user_query=user_query,
            response_text=response_text,
            recent_suggestions=recent,
            max_items=min(max_items, 5),
        )
        self.last_trace = {
            "suggestion_source": "intent_fallback",
            "provider_error_category": provider_error_category,
            "suggestions_before_filter": [item.text for item in generated],
            "suggestions_after_filter": [item.text for item in fallback],
            "rejected_reasons": rejected,
        }
        return fallback

    def _generate_with_ai(
        self,
        *,
        category: str,
        user_query: str,
        response_text: str,
        intent: str | None,
        retrieval_scope: str | None,
        output_format: str | None,
        intent_domain: str | None,
        intent_subdomain: str | None,
        conversation_context: dict,
        max_items: int,
    ) -> tuple[list[SuggestionItem], str | None]:
        instructions = (
            "You are CEASER's next-action generator.\n"
            "Return only concise next actions for the current answer.\n"
            "Return JSON only in this schema:\n"
            "{\"suggestions\":[{\"text\":\"...\",\"action_type\":\"...\",\"category\":\"...\",\"confidence\":0.0}]}\n"
            "Rules:\n"
            "- Generate 3 to 5 suggestions.\n"
            "- Use imperative action phrasing.\n"
            "- Normally keep each suggestion between 2 and 7 words.\n"
            "- Directly continue the current topic.\n"
            "- Suggest only things CEASER can actually help perform.\n"
            "- Avoid repeating the user's original request.\n"
            "- Avoid duplicates.\n"
            "- Do not mention CEASER itself.\n"
            "- Do not use question phrasing.\n"
            "- Never generate: Can CEASER..., Would you like..., How is..., Tell me more, Learn more, Continue exploring, Ask another question, More details.\n"
            "- Prefer actions such as: Create a timeline, Compare with Mahabharata, Generate quiz questions, Build a budget table, Show a code example, Create a competitor matrix.\n"
            "- If the answer is weakly specified, still give concrete actions instead of generic filler.\n"
        )
        input_text = json.dumps(
            {
                "user_query": user_query,
                "response_text": response_text[:4500],
                "intent": intent,
                "intent_domain": intent_domain,
                "intent_subdomain": intent_subdomain,
                "retrieval_scope": retrieval_scope,
                "output_format": output_format,
                "category_hint": category,
                "available_features": sorted(AVAILABLE_FEATURES),
                "recent_topic": conversation_context.get("inferred_topic"),
                "max_items": max(3, min(max_items, 5)),
            },
            ensure_ascii=False,
        )
        try:
            raw = generate_text_sync(
                instructions=instructions,
                input_text=input_text,
                temperature=0.15,
                max_output_tokens=260,
            )
            return self._parse_ai_suggestions(raw, category=category), None
        except AIServiceUnavailableError as exc:
            return [], exc.category
        except Exception:
            return [], "unexpected"

    def _parse_ai_suggestions(self, raw: str, *, category: str) -> list[SuggestionItem]:
        cleaned = raw.strip()
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned, flags=re.I)
        cleaned = re.sub(r"\s*```$", "", cleaned)
        start = cleaned.find("{")
        end = cleaned.rfind("}")
        if start >= 0 and end > start:
            cleaned = cleaned[start : end + 1]
        payload = json.loads(cleaned)
        suggestions = payload.get("suggestions") if isinstance(payload, dict) else []
        if not isinstance(suggestions, list):
            return []

        results: list[SuggestionItem] = []
        for item in suggestions:
            if isinstance(item, str):
                text = item.strip()
                action_type = "follow_up"
                item_category = category
                confidence = 0.75
            elif isinstance(item, dict):
                text = str(item.get("text", "")).strip()
                action_type = str(item.get("action_type", "follow_up")).strip() or "follow_up"
                item_category = str(item.get("category", category)).strip() or category
                try:
                    confidence = float(item.get("confidence", 0.75))
                except (TypeError, ValueError):
                    confidence = 0.75
            else:
                continue
            if not text:
                continue
            results.append(
                SuggestionItem(
                    text=self._normalize_text(text),
                    action_type=self._normalize_action_type(action_type),
                    category=self._normalize_category(item_category, category),
                    confidence=max(0.0, min(confidence, 1.0)),
                )
            )
        return results

    def _validate_suggestions(
        self,
        suggestions: list[SuggestionItem],
        *,
        user_query: str,
        response_text: str,
        category: str,
        recent_suggestions: list[str],
        max_items: int,
    ) -> tuple[list[SuggestionItem], list[dict[str, str]]]:
        recent_normalized = {self._normalize_key(item) for item in recent_suggestions}
        query_words = set(self._normalize_key(user_query).split())
        response_words = set(self._normalize_key(response_text).split())
        allowed_actions = self._allowed_action_types(category)
        results: list[SuggestionItem] = []
        rejected: list[dict[str, str]] = []
        seen: list[str] = []

        for suggestion in suggestions:
            text = self._normalize_text(suggestion.text)
            normalized = self._normalize_key(text)
            reason = self._rejection_reason(
                text=text,
                normalized=normalized,
                query_words=query_words,
                response_words=response_words,
                category=category,
                recent_normalized=recent_normalized,
                seen=seen,
                action_type=suggestion.action_type,
                allowed_actions=allowed_actions,
            )
            if reason:
                rejected.append({"text": text, "reason": reason})
                continue
            seen.append(normalized)
            results.append(
                SuggestionItem(
                    text=text,
                    action_type=suggestion.action_type,
                    category=category,
                    confidence=suggestion.confidence,
                )
            )
            if len(results) >= max_items:
                break
        return results, rejected

    def _rejection_reason(
        self,
        *,
        text: str,
        normalized: str,
        query_words: set[str],
        response_words: set[str],
        category: str,
        recent_normalized: set[str],
        seen: list[str],
        action_type: str,
        allowed_actions: set[str],
    ) -> str | None:
        if not normalized:
            return "empty"
        if normalized.startswith(BANNED_PREFIXES):
            return "banned_prefix"
        if "ceaser" in normalized:
            return "self_reference"
        word_count = len(text.split())
        if word_count < 2 or word_count > 10:
            return "invalid_length"
        if not self._starts_with_action_verb(text):
            return "not_actionable"
        if normalized in recent_normalized:
            return "recent_duplicate"
        if any(self._similarity(normalized, existing) >= 0.86 for existing in seen):
            return "duplicate"
        if self._too_close_to_user_request(normalized, query_words):
            return "repeats_user_request"
        if not self._looks_domain_relevant(normalized, category, response_words):
            return "low_relevance"
        if action_type not in allowed_actions:
            return "unsupported_action"
        return None

    def _intent_fallback(
        self,
        *,
        category: str,
        user_query: str,
        response_text: str,
        recent_suggestions: list[str],
        max_items: int,
    ) -> list[SuggestionItem]:
        combined = f"{user_query}\n{response_text}".lower()
        if category == "education" and any(token in combined for token in ["study", "exam", "revision", "schedule", "plan"]):
            pool = [
                ("Build a study timetable", "create_timetable"),
                ("Create quiz questions", "generate_questions"),
                ("Summarize key ideas", "summarize"),
                ("Explain with examples", "examples"),
                ("Compare related concepts", "compare"),
            ]
        elif category == "education" and any(token in combined for token in ["ramayana", "mahabharata", "krishna", "story", "character", "mythology", "lessons"]):
            pool = [
                ("Summarize the main story", "summarize"),
                ("List the key traits", "extract"),
                ("Explain the life lessons", "examples"),
                ("Compare related characters", "compare"),
                ("Build a timeline", "create_timeline"),
            ]
        elif category == "technology" and any(token in combined for token in ["aws", "azure", "cloud", "pricing", "services"]):
            pool = [
                ("Compare pricing models", "compare"),
                ("Compare core services", "compare_alternatives"),
                ("Build a comparison table", "create_table"),
                ("Recommend by use case", "research"),
                ("Compare AI services", "compare"),
            ]
        elif category == "creative" and any(token in combined for token in ["logo", "branding", "brand", "palette", "typography"]):
            pool = [
                ("Generate logo concepts", "create_outline"),
                ("Choose a color palette", "add_examples"),
                ("Create typography ideas", "rewrite"),
                ("Design brand guidelines", "create_table"),
                ("Refine the visual style", "rewrite"),
            ]
        elif category == "career" and any(token in combined for token in ["interview", "technical round", "hr round", "behavioral"]):
            pool = [
                ("Create model answers", "create_outline"),
                ("Run a mock interview", "step_by_step"),
                ("Generate technical round", "generate_questions"),
                ("Generate HR questions", "generate_questions"),
                ("Create evaluation rubric", "compare"),
            ]
        elif category == "finance" and any(token in combined for token in ["gst", "tax", "taxation", "filing", "registration", "compliance"]):
            pool = [
                ("Compare GST types", "compare"),
                ("Show a calculation example", "calculate"),
                ("Explain GST registration", "summarize"),
                ("List filing steps", "list"),
                ("Outline compliance basics", "create_outline"),
            ]
        else:
            pool = INTENT_FALLBACKS.get(category, INTENT_FALLBACKS["general"])
        recent_normalized = {self._normalize_key(item) for item in recent_suggestions}
        query_words = set(self._normalize_key(user_query).split())
        response_words = set(self._normalize_key(response_text).split())
        allowed_actions = self._allowed_action_types(category)
        results: list[SuggestionItem] = []
        seen: list[str] = []
        for text, action_type in pool:
            normalized = self._normalize_key(text)
            reason = self._rejection_reason(
                text=text,
                normalized=normalized,
                query_words=query_words,
                response_words=response_words,
                category=category,
                recent_normalized=recent_normalized,
                seen=seen,
                action_type=action_type,
                allowed_actions=allowed_actions,
            )
            if reason:
                continue
            seen.append(normalized)
            results.append(SuggestionItem(text=text, action_type=action_type, category=category, confidence=0.62))
            if len(results) >= max_items:
                break
        return results or [
            SuggestionItem(text=text, action_type=action_type, category="general", confidence=0.58)
            for text, action_type in INTENT_FALLBACKS["general"][:max_items]
        ]

    def _detect_category(
        self,
        *,
        user_query: str,
        response_text: str,
        intent: str | None,
        retrieval_scope: str | None,
        output_format: str | None,
        intent_domain: str | None,
        intent_subdomain: str | None,
    ) -> str:
        text = f"{user_query}\n{response_text}".lower()
        normalized_domain = (intent_domain or "").lower()
        normalized_subdomain = (intent_subdomain or "").lower()
        normalized_intent = (intent or "").lower()
        normalized_scope = (retrieval_scope or "").lower()
        normalized_format = (output_format or "").lower()

        if normalized_subdomain in {"cloud_comparison", "cloud_platforms"}:
            return "technology"
        if normalized_subdomain == "branding_design":
            return "creative"
        if normalized_subdomain == "interview_preparation":
            return "career"
        if normalized_subdomain in {"taxation", "financial_planning"} or normalized_domain == "finance":
            return "finance"
        if normalized_subdomain == "trip_planning" or normalized_domain == "travel":
            return "travel"
        if normalized_subdomain == "mythology":
            return "education"
        if normalized_subdomain == "science":
            return "education"
        if normalized_subdomain == "coding":
            return "programming"
        if normalized_subdomain == "strategy":
            return "business"
        if normalized_subdomain == "writing":
            return "writing"

        if any(token in text for token in ["trip", "travel", "itinerary", "flight", "hotel", "visa", "destination"]):
            return "travel"
        if any(token in text for token in ["study", "exam", "revision", "flashcard", "mcq", "notes", "chapter", "syllabus", "ramayana", "mahabharata", "krishna", "gst", "black hole"]):
            return "education"
        if any(token in text for token in ["python", "javascript", "react", "api", "bug", "code", "debug", "algorithm", "sql", "kubernetes", "aws", "azure"]):
            return "programming"
        if any(token in text for token in ["startup", "business", "market", "competitor", "pitch", "revenue", "gtm", "sales", "marketing strategy"]):
            return "business"
        if any(token in text for token in ["write", "essay", "caption", "draft", "email", "blog", "linkedin", "cover letter", "presentation outline", "logo"]):
            return "writing"
        if any(token in text for token in ["research", "source", "citation", "latest", "report", "analysis", "findings", "pdf"]):
            return "research"
        if any(token in text for token in ["schedule", "task", "calendar", "plan my day", "todo", "workflow", "productivity", "workout plan"]):
            return "productivity"
        if any(token in text for token in ["finance", "stock", "budget", "investment", "profit", "cash flow", "pricing", "monthly budget"]):
            return "finance"
        if any(token in text for token in ["health", "fitness", "diet", "medical", "symptom", "wellness", "sleep"]):
            return "health"

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

    def _allowed_action_types(self, category: str) -> set[str]:
        mapping = {
            "education": {"summarize", "generate_questions", "compare", "create_timeline", "examples", "extract", "timeline", "create_timetable"},
            "programming": {"code_example", "generate_tests", "step_by_step", "compare", "debug", "code", "test", "workflow"},
            "technology": {"compare", "create_table", "create_chart", "estimate_metrics", "research", "compare_alternatives"},
            "business": {"action_plan", "compare_competitors", "pitch_outline", "estimate_metrics", "export_report", "create", "draft", "export", "compare"},
            "finance": {"budget_table", "create_chart", "compare_categories", "calculate", "monthly_plan", "chart", "list", "create_outline", "summarize"},
            "research": {"extract_findings", "compare_sources", "create_timeline", "summary_table", "research_questions", "generate_report", "extract_key_points", "generate_quiz", "compare_with", "export_table"},
            "travel": {"itinerary", "estimate_budget", "compare_destinations", "travel_requirements", "best_season"},
            "writing": {"create_outline", "rewrite", "shorten", "add_examples", "turn_into_slides", "draft_email", "convert", "add"},
            "creative": {"create_outline", "rewrite", "add_examples", "create_chart", "create_table", "turn_into_slides"},
            "career": {"generate_questions", "step_by_step", "compare", "draft_email", "create_outline"},
            "productivity": {"create", "export", "compare", "chart", "checklist", "calendar_create"},
            "health": {"summarize", "compare", "plan", "list"},
            "general": {"summarize", "examples", "compare", "explain"},
        }
        return mapping.get(category, mapping["general"])

    def _looks_domain_relevant(self, normalized: str, category: str, response_words: set[str]) -> bool:
        category_keywords = {
            "education": {"timeline", "quiz", "concept", "lesson", "examples", "characters", "ideas"},
            "programming": {"code", "tests", "debug", "implementation", "alternatives", "step"},
            "technology": {"pricing", "services", "comparison", "table", "cloud", "architecture", "use", "models", "recommend", "cases"},
            "business": {"plan", "competitors", "pitch", "metrics", "report", "matrix"},
            "finance": {"budget", "chart", "spending", "percentages", "monthly", "table", "gst", "registration", "filing", "compliance", "calculation"},
            "research": {"findings", "sources", "timeline", "summary", "questions", "table"},
            "travel": {"itinerary", "budget", "destinations", "requirements", "season"},
            "writing": {"outline", "rewrite", "shorten", "examples", "slides"},
            "creative": {"palette", "typography", "guidelines", "concepts", "branding", "logo"},
            "career": {"interview", "answers", "practice", "questions", "round"},
            "productivity": {"schedule", "checklist", "calendar", "plan", "chart"},
            "health": {"routine", "compare", "precautions", "signs"},
            "general": {"summarize", "examples", "compare", "key"},
        }
        keywords = category_keywords.get(category, category_keywords["general"])
        return any(word in normalized for word in keywords) or bool(set(normalized.split()) & response_words)

    def _starts_with_action_verb(self, text: str) -> bool:
        first = self._normalize_key(text).split()
        return bool(first and first[0] in ACTION_VERBS)

    def _too_close_to_user_request(self, normalized: str, query_words: set[str]) -> bool:
        words = set(normalized.split())
        if not words:
            return True
        overlap = words & query_words
        return len(words) >= 3 and len(overlap) / max(1, len(words)) > 0.8

    def _normalize_text(self, text: str) -> str:
        cleaned = re.sub(r"\s+", " ", text.strip())
        cleaned = cleaned.rstrip("?.!,;:")
        if len(cleaned) > 56:
            cleaned = cleaned[:56].rstrip(" ,.;:")
        return cleaned[:1].upper() + cleaned[1:] if cleaned else cleaned

    def _normalize_action_type(self, action_type: str) -> str:
        cleaned = self._normalize_key(action_type)
        return cleaned.replace(" ", "_") or "follow_up"

    def _normalize_category(self, category: str, fallback: str) -> str:
        cleaned = self._normalize_key(category).replace(" ", "_")
        return cleaned or fallback

    def _normalize_key(self, text: str) -> str:
        return re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()

    def _similarity(self, left: str, right: str) -> float:
        return SequenceMatcher(None, left, right).ratio()
