from __future__ import annotations

from dataclasses import asdict
import logging
from time import perf_counter

from sqlalchemy.orm import Session

from app.core.config.settings import settings
from app.intelligence.ai.errors import AIServiceUnavailableError
from app.intelligence.ai.ai_provider_service import ai_provider_service
from app.intelligence.formatting.response_formatter import response_formatter
from app.intelligence.knowledge.context_builder import context_builder
from app.intelligence.knowledge.engine import KnowledgeEngine
from app.intelligence.knowledge.repository import KnowledgeRepository
from app.intelligence.orchestrator.intent_engine import intent_engine
from app.intelligence.orchestrator.models import IntentType, RequestContext, RetrievalPlan
from app.intelligence.orchestrator.retrieval_planner import retrieval_planner


logger = logging.getLogger(__name__)


class RequestOrchestrator:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.knowledge_engine = KnowledgeEngine(db)
        self.repository = KnowledgeRepository(db)
        self.last_llm_provider_name: str | None = None

    async def handle(self, request: RequestContext) -> dict:
        started = perf_counter()
        intent = await intent_engine.classify(request)
        plan = await retrieval_planner.build(request=request, intent=intent)
        items = await self.knowledge_engine.retrieve(request=request, plan=plan)
        context = context_builder.build(request=request, items=items)
        if not plan.needs_generation:
            domain_result = self._domain_result(intent=intent, plan=plan, context_items=len(items))
        else:
            domain_result = await self._generate_with_fallback(
                instructions=self._instructions_for(intent),
                input_text=context.to_prompt(request.message),
            )
        response = response_formatter.format(intent=intent, domain_result=domain_result, context=context)
        provider_name = self.last_llm_provider_name
        self.repository.record_context_run(
            user_id=request.user_id,
            conversation_id=request.conversation_id,
            intent=intent.value,
            retrieval_plan=self._plan_dict(plan),
            selected_context=[asdict(item) for item in context.items],
            output_format=plan.output_format,
            model_provider=provider_name if plan.needs_generation else None,
            model_name=self._model_name_for(provider_name) if plan.needs_generation else None,
            started=started,
        )
        return response

    async def _generate_with_fallback(self, *, instructions: str, input_text: str) -> str:
        last_error: Exception | None = None
        attempts = ai_provider_service.llm.candidates(max_count=max(1, settings.llm_max_fallbacks + 1))
        if not attempts:
            raise AIServiceUnavailableError("No LLM provider is configured.", retryable=False, category="configuration")
        for index, (provider_name, llm) in enumerate(attempts):
            started = perf_counter()
            try:
                result = await llm.generate(instructions=instructions, input_text=input_text)
                self.last_llm_provider_name = provider_name
                logger.info("AI provider succeeded: provider=%s total_ms=%s", provider_name, round((perf_counter() - started) * 1000))
                return result
            except AIServiceUnavailableError as exc:
                last_error = exc
                ai_provider_service.llm.router.record_failure(provider_name, exc)
                logger.warning(
                    "AI provider failed: provider=%s retryable=%s category=%s detail=%s",
                    provider_name,
                    exc.retryable,
                    exc.category,
                    exc.detail,
                )
                if not exc.retryable or index >= len(attempts) - 1:
                    break
            except Exception as exc:  # noqa: BLE001
                last_error = AIServiceUnavailableError(repr(exc), retryable=True, provider=provider_name, category="unexpected")
                ai_provider_service.llm.router.record_failure(provider_name, last_error)
                logger.warning("AI provider failed unexpectedly: provider=%s error=%s", provider_name, repr(exc))
                if index >= len(attempts) - 1:
                    break
        raise AIServiceUnavailableError(repr(last_error), retryable=False)

    def _domain_result(self, *, intent: IntentType, plan: RetrievalPlan, context_items: int) -> dict:
        return {
            "type": plan.output_format,
            "message": "Structured result ready.",
            "count": context_items,
            "intent": intent.value,
        }

    def _instructions_for(self, intent: IntentType) -> str:
        return (
            "You are CEASER, a personal AI operating system. Answer using only the relevant evidence when evidence is provided. "
            "Choose the format that fits the user request. Do not force every answer into Executive Summary, Key Trends, and Recommendations. "
            f"Intent: {intent.value}."
        )

    def _plan_dict(self, plan: RetrievalPlan) -> dict:
        return {
            "intent": plan.intent.value,
            "providers": [asdict(provider) for provider in plan.providers],
            "needs_generation": plan.needs_generation,
            "output_format": plan.output_format,
            "requires_confirmation": plan.requires_confirmation,
        }

    def _model_name_for(self, provider_name: str | None) -> str | None:
        if provider_name == "groq":
            return settings.groq_model
        if provider_name == "huggingface":
            return settings.huggingface_model
        if provider_name == "gemini":
            return settings.gemini_model
        if provider_name == "openai":
            return settings.openai_model
        return None
