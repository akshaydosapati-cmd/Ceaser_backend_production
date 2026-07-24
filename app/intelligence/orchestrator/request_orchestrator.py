from __future__ import annotations

from dataclasses import asdict
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


class RequestOrchestrator:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.knowledge_engine = KnowledgeEngine(db)
        self.repository = KnowledgeRepository(db)

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
        self.repository.record_context_run(
            user_id=request.user_id,
            conversation_id=request.conversation_id,
            intent=intent.value,
            retrieval_plan=self._plan_dict(plan),
            selected_context=[asdict(item) for item in context.items],
            output_format=plan.output_format,
            model_provider=settings.llm_provider if plan.needs_generation else None,
            model_name=settings.openai_model if settings.llm_provider.lower() == "openai" else settings.gemini_model,
            started=started,
        )
        return response

    async def _generate_with_fallback(self, *, instructions: str, input_text: str) -> str:
        last_error: Exception | None = None
        for llm in (ai_provider_service.llm.production(), ai_provider_service.llm.fallback()):
            try:
                return await llm.generate(instructions=instructions, input_text=input_text)
            except Exception as exc:
                last_error = exc
        raise AIServiceUnavailableError(repr(last_error))

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
