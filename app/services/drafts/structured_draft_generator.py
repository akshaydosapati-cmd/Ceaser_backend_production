from __future__ import annotations

import json
import logging
import re

from app.intelligence.ai.sync import generate_text_sync
from app.services.drafts.draft_schema_registry import DraftSchemaRegistry
from app.services.drafts.draft_validator import DraftValidationError, DraftValidator
from app.services.llm.gemini_provider import GeminiProvider

logger = logging.getLogger(__name__)


class DraftGenerationError(RuntimeError):
    pass


class StructuredDraftGenerator:
    def generate(self, *, prompt: str, draft_type: str, agent_id: str, title: str, target_app: str, requested_units: int, context: dict | None = None) -> dict:
        schema = DraftSchemaRegistry().get(draft_type)
        effective_target = target_app if target_app != "keep_as_draft" else schema.get("target_app", target_app)
        if draft_type == "pitch_deck":
            try:
                deck = self._generate_slide_deck(
                    prompt=prompt,
                    draft_type=draft_type,
                    agent_id=agent_id,
                    title=title,
                    target_app=effective_target,
                    requested_units=requested_units,
                    schema=schema,
                    context=context or {},
                )
                return DraftValidator().validate(deck, draft_type)
            except (DraftValidationError, json.JSONDecodeError, TypeError, ValueError) as exc:
                logger.warning("Slide deck generation failed (%s/%s); falling back to structured JSON path: %s", agent_id, draft_type, exc)
        if self._uses_section_pipeline(draft_type):
            try:
                planned = self._generate_section_document(
                    prompt=prompt,
                    draft_type=draft_type,
                    agent_id=agent_id,
                    title=title,
                    target_app=effective_target,
                    requested_units=requested_units,
                    schema=schema,
                    context=context or {},
                )
                return DraftValidator().validate(planned, draft_type)
            except (DraftValidationError, json.JSONDecodeError, TypeError, ValueError) as exc:
                logger.warning("Section draft generation failed (%s/%s); falling back to structured JSON path: %s", agent_id, draft_type, exc)
        last_error = "Unknown validation error."
        for strictness in ["strict", "repair"]:
            response = self._generate_provider_json_text(
                self._prompt(prompt, title, draft_type, agent_id, effective_target, requested_units, schema, strictness, context or {})
            )
            logger.info("Raw structured draft provider response (%s/%s): %s", agent_id, draft_type, response)
            try:
                return DraftValidator().validate(self._extract_json(response), draft_type)
            except (DraftValidationError, json.JSONDecodeError, TypeError) as exc:
                last_error = str(exc)
                logger.warning("Structured draft validation failed (%s/%s/%s): %s", agent_id, draft_type, strictness, exc)
                try:
                    repaired = self._repair_response(response=response, error=str(exc), schema=schema)
                    return DraftValidator().validate(self._extract_json(repaired), draft_type)
                except (DraftValidationError, json.JSONDecodeError, TypeError) as repair_exc:
                    last_error = str(repair_exc)
                    logger.warning("Structured draft repair failed (%s/%s/%s): %s", agent_id, draft_type, strictness, repair_exc)
                continue
        logger.error("Gemini structured draft failed; using deterministic fallback (%s/%s): %s", agent_id, draft_type, last_error)
        fallback = self._fallback_content(prompt=prompt, title=title, draft_type=draft_type, agent_id=agent_id, target_app=effective_target, requested_units=requested_units)
        return DraftValidator().validate(self._ensure_schema_keys(fallback, schema, prompt=prompt, title=title, agent_id=agent_id), draft_type)

    def _uses_section_pipeline(self, draft_type: str) -> bool:
        return draft_type in {
            "business_plan",
            "go_to_market_plan",
            "campaign_plan",
            "social_strategy",
            "content_pack",
            "technical_spec",
            "api_documentation",
            "implementation_plan",
            "goal_plan",
            "travel_plan",
            "architecture_plan",
            "study_plan",
            "learning_roadmap",
        }

    def _generate_section_document(
        self,
        *,
        prompt: str,
        draft_type: str,
        agent_id: str,
        title: str,
        target_app: str,
        requested_units: int,
        schema: dict,
        context: dict,
    ) -> dict:
        topic = self._topic(prompt, title)
        count = max(3, min(requested_units, 12))
        headings = self._headings_for(draft_type, count)
        base = {
            "title": title,
            "type": draft_type,
            "draft_type": draft_type,
            "owner_agent": agent_id,
            "target_app": target_app,
            "sections": [],
        }
        for index, heading in enumerate(headings, start=1):
            section = self._generate_single_section(
                prompt=prompt,
                topic=topic,
                draft_type=draft_type,
                agent_id=agent_id,
                title=title,
                heading=heading,
                section_number=index,
                total_sections=len(headings),
                context=context,
            )
            base["sections"].append(section)
        return self._ensure_schema_keys(base, schema, prompt=prompt, title=title, agent_id=agent_id)

    def _generate_single_section(
        self,
        *,
        prompt: str,
        topic: str,
        draft_type: str,
        agent_id: str,
        title: str,
        heading: str,
        section_number: int,
        total_sections: int,
        context: dict,
    ) -> dict:
        section_prompt = self._section_prompt(
            prompt=prompt,
            topic=topic,
            draft_type=draft_type,
            agent_id=agent_id,
            title=title,
            heading=heading,
            section_number=section_number,
            total_sections=total_sections,
            context=context,
        )
        try:
            response = self._generate_provider_json_text(section_prompt)
            section = self._extract_json(response)
            return self._normalize_section(section, heading=heading, topic=topic, agent_id=agent_id)
        except (json.JSONDecodeError, TypeError, ValueError) as exc:
            logger.warning("Single section generation failed (%s/%s/%s): %s", agent_id, draft_type, heading, exc)
            return self._fallback_section(heading=heading, topic=topic, agent_id=agent_id, draft_type=draft_type)

    def _generate_provider_json_text(self, prompt: str) -> str:
        try:
            return generate_text_sync(
                instructions=(
                    "You are CEASER structured draft generation. Return valid JSON only. "
                    "Never include markdown fences, placeholder text, or meta commentary."
                ),
                input_text=prompt,
                temperature=0.2,
                max_output_tokens=2400,
            )
        except Exception:
            return GeminiProvider().generate_response(prompt, {"structured_draft_json": True})

    def _section_prompt(
        self,
        *,
        prompt: str,
        topic: str,
        draft_type: str,
        agent_id: str,
        title: str,
        heading: str,
        section_number: int,
        total_sections: int,
        context: dict,
    ) -> str:
        return (
            "Return valid JSON only. No markdown. No prose outside JSON.\n"
            "You are writing ONE finished document section, not an outline and not instructions.\n"
            "Write concrete, domain-specific content that can be shown directly to a user in a V1 demo.\n"
            "Never write meta-actions such as clarify, review assumptions, connect context, identify action, or convert insight.\n"
            "Never use placeholders, TBD, template text, or generic filler.\n"
            "Use the user's request, CEASER memory, uploaded file excerpts, and research context when available.\n"
            "If context is limited, infer responsibly and write useful professional content.\n"
            "Output exactly this JSON shape:\n"
            "{\"heading\":\"...\",\"summary\":\"2-4 complete sentences\",\"details\":[\"specific point\",\"specific point\",\"specific point\",\"specific point\"],\"recommendations\":[\"specific recommendation\",\"specific recommendation\",\"specific recommendation\"]}\n"
            f"Document title: {title}\n"
            f"Document type: {draft_type}\n"
            f"Owner agent: {agent_id}\n"
            f"Section {section_number} of {total_sections}: {heading}\n"
            f"Overall user request: {prompt}\n"
            f"Topic: {topic}\n"
            f"Relevant memories: {json.dumps(context.get('memories', []))}\n"
            f"Uploaded file excerpts: {json.dumps(context.get('files', []))}\n"
            f"Research context: {json.dumps(context.get('research', {}))}\n"
        )

    def _normalize_section(self, section: dict, *, heading: str, topic: str, agent_id: str) -> dict:
        if not isinstance(section, dict):
            raise ValueError("Section response must be a JSON object.")
        normalized = {
            "heading": str(section.get("heading") or heading).strip(),
            "summary": str(section.get("summary") or self._section_summary(heading, topic)).strip(),
            "details": self._clean_list(section.get("details"), fallback=self._bullets(heading, topic, agent_id)),
            "recommendations": self._clean_list(section.get("recommendations"), fallback=self._recommendations(heading, topic)),
        }
        DraftValidator().validate({"draft_type": "business_plan", "target_app": "word", "sections": [normalized]}, "business_plan")
        return normalized

    def _fallback_section(self, *, heading: str, topic: str, agent_id: str, draft_type: str) -> dict:
        if draft_type == "business_plan":
            for section in self._business_plan_sections(topic):
                if section["heading"].lower() == heading.lower():
                    return section
        return {
            "heading": heading,
            "summary": self._section_summary(heading, topic),
            "details": self._bullets(heading, topic, agent_id),
            "recommendations": self._recommendations(heading, topic),
        }

    @staticmethod
    def _clean_list(value, *, fallback: list[str]) -> list[str]:
        if isinstance(value, list):
            cleaned = [str(item).strip() for item in value if str(item).strip()]
        elif isinstance(value, str) and value.strip():
            cleaned = [value.strip()]
        else:
            cleaned = []
        return cleaned[:6] or fallback

    @staticmethod
    def _slide_names(count: int) -> list[str]:
        return ["Title", "Problem", "Solution", "Market", "Product", "Business Model", "Traction", "Go-To-Market", "Ask"][:count]

    def _fallback_slide(self, *, slide_name: str, slide_number: int, topic: str) -> dict:
        return {
            "slide_number": slide_number,
            "title": self._slide_title(slide_name, topic),
            "purpose": self._slide_purpose(slide_name, topic),
            "bullets": self._slide_bullets(slide_name, topic),
            "visual_suggestion": self._slide_visual(slide_name, topic),
            "speaker_notes": self._slide_notes(slide_name, topic),
            "memory_references": [],
            "source_references": [],
        }

    def _slide_title(self, slide_name: str, topic: str) -> str:
        subject = self._business_subject(topic)
        lower = slide_name.lower()
        if lower == "title":
            return subject
        return slide_name

    def _slide_purpose(self, slide_name: str, topic: str) -> str:
        subject = self._business_subject(topic)
        lower = slide_name.lower()
        if lower == "title":
            return f"Position {subject} as a secure, practical health record platform for clinics and patients."
        if lower == "problem":
            return "Show why fragmented health records create operational, clinical, and trust problems."
        if lower == "solution":
            return f"Show how {subject} unifies records, access, and sharing in one secure workflow."
        if lower == "market":
            return "Show the launch opportunity across independent clinics, diagnostic centers, and chronic-care patients."
        if lower == "product":
            return "Show the core product experience and the first workflow users can understand immediately."
        if lower == "business model":
            return "Show how the company can earn recurring revenue while protecting patient trust."
        if lower == "traction":
            return "Show current validation, pilots, usage signals, or the immediate validation plan."
        if lower == "go-to-market":
            return "Show the first repeatable path to acquire clinics and onboard patients."
        if lower == "ask":
            return "Show the specific support needed to reach the next milestone."
        return f"Explain the strategic role of this slide for {subject}."

    def _slide_bullets(self, slide_name: str, topic: str) -> list[str]:
        subject = self._business_subject(topic)
        lower = slide_name.lower()
        if lower == "title":
            return [
                "Secure digital health record management for modern clinics.",
                "Organizes patient records, documents, and care history in one trusted workspace.",
                "Helps healthcare teams access accurate patient context faster.",
            ]
        if lower == "problem":
            return [
                "Patient records are scattered across paper files, PDFs, lab portals, WhatsApp, and disconnected clinic tools.",
                "Doctors and staff lose time retrieving old reports, prescriptions, and care history during visits.",
                "Informal sharing creates privacy risk and weak continuity of care for patients.",
            ]
        if lower == "solution":
            return [
                f"{subject} gives patients and clinics one secure place to store, organize, retrieve, and share health records.",
                "AI helps classify documents, summarize medical history, and surface relevant context before consultation.",
                "Consent-based sharing lets clinics access the right information without depending on messy manual handoffs.",
            ]
        if lower == "market":
            return [
                "India's clinics and diagnostic centers are moving toward digital workflows, but many still lack simple record interoperability.",
                "Independent and specialty clinics need practical tools that are lighter than hospital-grade EHR systems.",
                "Hyderabad is a strong early launch market because of healthcare density and startup-friendly adoption channels.",
            ]
        if lower == "product":
            return [
                "Patient health timeline for prescriptions, lab reports, scans, invoices, and doctor notes.",
                "Clinic dashboard for authorized record access, document search, and summarized patient context.",
                "Secure sharing, OCR extraction, and structured metadata designed for future integrations.",
            ]
        if lower == "business model":
            return [
                "B2B subscriptions for clinics using staff accounts, patient record access, and workflow tools.",
                "Freemium patient locker with paid family profiles, higher storage, and smart summaries.",
                "Partner channels with diagnostic labs and specialty clinics can reduce acquisition cost over time.",
            ]
        if lower == "traction":
            return [
                "Start with pilot clinics to validate onboarding, record retrieval time, and repeat patient usage.",
                "Track uploaded records, active patients, staff usage, and consultation time saved.",
                "Convert the strongest pilot into a case study for the next wave of clinic acquisition.",
            ]
        if lower == "go-to-market":
            return [
                "Begin with founder-led outreach to independent clinics and diagnostic centers in Hyderabad.",
                "Use doctor-led patient onboarding through QR invites, clinic visits, and follow-up workflows.",
                "Build trust with a simple demo: upload, classify, retrieve, and securely share a patient record.",
            ]
        if lower == "ask":
            return [
                "Seeking pilot partners, healthcare advisors, and early users to validate the first clinic workflow.",
                "Next milestone: launch pilots, measure usage, and convert early clinics into paid customers.",
                "Support needed: clinical feedback, product validation, and introductions to clinic decision-makers.",
            ]
        return self._bullets(slide_name, topic, "zeus")[:3]

    def _slide_visual(self, slide_name: str, topic: str) -> str:
        subject = self._business_subject(topic)
        lower = slide_name.lower()
        if lower == "title":
            return f"Hero visual of the {subject} dashboard beside a clean patient health timeline on mobile."
        if lower == "problem":
            return "Split-screen showing paper files, WhatsApp reports, and scattered PDFs on the left versus a delayed clinic consultation on the right."
        if lower == "solution":
            return f"Flow diagram: patient uploads record, {subject} organizes it, clinic accesses authorized summary before consultation."
        if lower == "market":
            return "India clinic market map with focus on independent clinics, diagnostic centers, and chronic-care patients."
        if lower == "product":
            return "Three-panel product mockup: patient timeline, clinic dashboard, and AI document summary."
        if lower == "business model":
            return "Revenue stack showing clinic subscription, patient premium, and partner channels."
        if lower == "traction":
            return "Pilot milestone chart with clinics signed, records uploaded, active users, and conversion targets."
        if lower == "go-to-market":
            return "Launch funnel from clinic outreach to pilot onboarding, patient invites, case study, and paid conversion."
        if lower == "ask":
            return "Milestone roadmap showing pilot launch, product validation, paid clinic conversion, and seed readiness."
        return f"Specific product or workflow visual for {subject}."

    def _slide_notes(self, slide_name: str, topic: str) -> str:
        subject = self._business_subject(topic)
        lower = slide_name.lower()
        if lower == "title":
            return f"{subject} is presented as a practical healthtech platform for clinics that need better patient record organization without the complexity of large hospital systems. The story starts with trust, speed, and continuity of care."
        if lower == "problem":
            return "The pain is not just storage. Clinics and patients lose time because important health context is scattered across many places, which creates repeated work and weak continuity of care."
        if lower == "solution":
            return f"{subject} solves this by becoming the secure record layer between patients and clinics. The product makes health records easier to organize, retrieve, summarize, and share with consent."
        if lower == "market":
            return "The first market should be narrow and reachable. Independent clinics and diagnostic centers are large enough to matter, but simple enough for a focused startup to serve well."
        if lower == "product":
            return "The product demo should show one complete workflow from upload to clinic access. If the audience understands that workflow quickly, the value becomes obvious."
        if lower == "business model":
            return "The cleanest early revenue path is clinic subscription revenue, supported by optional patient premium features later. The model should avoid monetizing sensitive health data."
        if lower == "traction":
            return "If hard traction numbers are not available yet, this slide should show the validation plan and the exact metrics the team will prove through pilots."
        if lower == "go-to-market":
            return "The launch motion is intentionally local and focused. Win a few clinics, produce measurable outcomes, then use those results to scale the next wave."
        if lower == "ask":
            return "The ask should be specific and tied to the next milestone. For a demo or early pitch, the best ask is pilot access, healthcare feedback, and introductions."
        return f"This slide should help the audience understand why {subject} matters now."

    def _generate_slide_deck(
        self,
        *,
        prompt: str,
        draft_type: str,
        agent_id: str,
        title: str,
        target_app: str,
        requested_units: int,
        schema: dict,
        context: dict,
    ) -> dict:
        topic = self._topic(prompt, title)
        count = max(3, min(requested_units, 12))
        slide_names = self._slide_names(count)
        base = {
            "title": title,
            "type": draft_type,
            "draft_type": draft_type,
            "owner_agent": agent_id,
            "target_app": target_app,
            "slides": [],
        }
        for index, slide_name in enumerate(slide_names, start=1):
            slide = self._generate_single_slide(
                prompt=prompt,
                topic=topic,
                agent_id=agent_id,
                title=title,
                slide_name=slide_name,
                slide_number=index,
                total_slides=len(slide_names),
                context=context,
            )
            base["slides"].append(slide)
        return self._ensure_schema_keys(base, schema, prompt=prompt, title=title, agent_id=agent_id)

    def _generate_single_slide(
        self,
        *,
        prompt: str,
        topic: str,
        agent_id: str,
        title: str,
        slide_name: str,
        slide_number: int,
        total_slides: int,
        context: dict,
    ) -> dict:
        slide_prompt = self._slide_prompt(
            prompt=prompt,
            topic=topic,
            agent_id=agent_id,
            title=title,
            slide_name=slide_name,
            slide_number=slide_number,
            total_slides=total_slides,
            context=context,
        )
        try:
            response = GeminiProvider().generate_response(slide_prompt, {"structured_draft_json": True})
            slide = self._extract_json(response)
            return self._normalize_slide(slide, slide_name=slide_name, slide_number=slide_number, topic=topic)
        except (json.JSONDecodeError, TypeError, ValueError) as exc:
            logger.warning("Single slide generation failed (%s/pitch_deck/%s): %s", agent_id, slide_name, exc)
            return self._fallback_slide(slide_name=slide_name, slide_number=slide_number, topic=topic)

    def _slide_prompt(
        self,
        *,
        prompt: str,
        topic: str,
        agent_id: str,
        title: str,
        slide_name: str,
        slide_number: int,
        total_slides: int,
        context: dict,
    ) -> str:
        return (
            "Return valid JSON only. No markdown. No prose outside JSON.\n"
            "You are writing ONE finished investor pitch deck slide, not a slide instruction and not a planner note.\n"
            "Write concise slide-ready content. Bullets must be content that appears on the slide.\n"
            "Speaker notes must be actual presenter notes, not instructions like 'talk through why'.\n"
            "Visual suggestion must describe a concrete visual scene or chart, not 'use a clean visual'.\n"
            "Never use placeholders, TBD, template text, or meta-actions such as clarify, review, explain clearly, connect context, or identify action.\n"
            "Output exactly this JSON shape:\n"
            "{\"title\":\"...\",\"purpose\":\"one sentence strategic role of this slide\",\"bullets\":[\"slide bullet\",\"slide bullet\",\"slide bullet\"],\"visual_suggestion\":\"specific visual direction\",\"speaker_notes\":\"2-4 complete sentences to present this slide\",\"memory_references\":[],\"source_references\":[]}\n"
            f"Deck title: {title}\n"
            f"Owner agent: {agent_id}\n"
            f"Slide {slide_number} of {total_slides}: {slide_name}\n"
            f"Overall user request: {prompt}\n"
            f"Topic: {topic}\n"
            f"Relevant memories: {json.dumps(context.get('memories', []))}\n"
            f"Uploaded file excerpts: {json.dumps(context.get('files', []))}\n"
            f"Research context: {json.dumps(context.get('research', {}))}\n"
        )

    def _normalize_slide(self, slide: dict, *, slide_name: str, slide_number: int, topic: str) -> dict:
        if not isinstance(slide, dict):
            raise ValueError("Slide response must be a JSON object.")
        normalized = {
            "slide_number": slide_number,
            "title": str(slide.get("title") or slide_name).strip(),
            "purpose": str(slide.get("purpose") or self._slide_purpose(slide_name, topic)).strip(),
            "bullets": self._clean_list(slide.get("bullets"), fallback=self._slide_bullets(slide_name, topic)),
            "visual_suggestion": str(slide.get("visual_suggestion") or self._slide_visual(slide_name, topic)).strip(),
            "speaker_notes": str(slide.get("speaker_notes") or self._slide_notes(slide_name, topic)).strip(),
            "memory_references": slide.get("memory_references") if isinstance(slide.get("memory_references"), list) else [],
            "source_references": slide.get("source_references") if isinstance(slide.get("source_references"), list) else [],
        }
        DraftValidator().validate({"draft_type": "pitch_deck", "target_app": "powerpoint", "slides": [normalized]}, "pitch_deck")
        return normalized

    def _prompt(self, prompt: str, title: str, draft_type: str, agent_id: str, target_app: str, requested_units: int, schema: dict, strictness: str, context: dict) -> str:
        return (
            "Return valid JSON only. No markdown. No prose outside JSON.\n"
            "Generate complete, investor/user-ready content. Fill every field with useful execution-ready content.\n"
            "Do not use placeholders, template text, 'point for', 'needs review', 'TBD', or generic filler.\n"
            "Use CEASER memories, uploaded file context, sources, and research context when provided.\n"
            "If context is limited, infer responsibly from the user request and produce specific useful content.\n"
            f"Strictness: {strictness}\n"
            f"Agent: {agent_id}\nDraft title: {title}\nDraft type: {draft_type}\nTarget app: {target_app}\nRequested units: {requested_units}\n"
            f"User request: {prompt}\n"
            f"CEASER memories: {json.dumps(context.get('memories', []))}\n"
            f"Uploaded files: {json.dumps(context.get('files', []))}\n"
            f"Research context: {json.dumps(context.get('research', {}))}\n"
            f"Match this schema exactly: {json.dumps(schema)}"
        )

    def _extract_json(self, response: str) -> dict:
        cleaned = response.strip()
        if cleaned.startswith("```"):
            cleaned = re.sub(r"^```(?:json)?", "", cleaned).strip()
            cleaned = re.sub(r"```$", "", cleaned).strip()
        match = re.search(r"\{.*\}", cleaned, re.S)
        candidate = match.group(0) if match else cleaned
        return json.loads(self._light_repair(candidate))

    def _light_repair(self, candidate: str) -> str:
        repaired = candidate.strip().replace("\ufeff", "")
        repaired = re.sub(r",\s*([}\]])", r"\1", repaired)
        return repaired

    def _repair_response(self, *, response: str, error: str, schema: dict) -> str:
        repair_prompt = (
            "Repair this malformed JSON and return valid JSON only. No markdown. No explanation.\n"
            "Keep the same content, but fix syntax errors and ensure it matches the required schema.\n"
            "Do not add placeholders, template text, 'point for', 'needs review', or 'TBD'.\n"
            f"Parser/validation error: {error}\n"
            f"Required schema: {json.dumps(schema)}\n"
            f"Malformed JSON/text:\n{response}"
        )
        return GeminiProvider().generate_response(repair_prompt, {"structured_draft_json": True})

    def _fallback_content(self, *, prompt: str, title: str, draft_type: str, agent_id: str, target_app: str, requested_units: int) -> dict:
        base = {
            "title": title,
            "type": draft_type,
            "draft_type": draft_type,
            "owner_agent": agent_id,
            "target_app": target_app,
        }
        topic = self._topic(prompt, title)
        count = max(3, min(requested_units, 12))
        if draft_type == "pitch_deck":
            return {
                **base,
                "slides": [
                    self._fallback_slide(slide_name=name, slide_number=index + 1, topic=topic)
                    for index, name in enumerate(self._slide_names(count))
                ],
            }
        if draft_type in {"business_plan", "go_to_market_plan", "campaign_plan", "social_strategy", "content_pack", "technical_spec", "api_documentation", "implementation_plan", "goal_plan", "travel_plan"}:
            headings = self._headings_for(draft_type, count)
            if draft_type == "business_plan":
                sections = self._business_plan_sections(topic)
            else:
                sections = [
                    {
                        "heading": heading,
                        "summary": self._section_summary(heading, topic),
                        "details": self._bullets(heading, topic, agent_id),
                        "recommendations": self._recommendations(heading, topic),
                    }
                    for heading in headings
                ]
            return {
                **base,
                "sections": sections[:count],
            }
        if draft_type in {"research_report", "competitor_analysis", "market_overview", "trend_report", "swot_report"}:
            content = {
                **base,
                "research_question": topic,
                "executive_summary": f"This report summarizes the most useful findings and decisions for {topic}.",
                "key_findings": [
                    {"finding": heading, "evidence": f"{heading} affects how {topic} should be positioned and executed.", "source_references": []}
                    for heading in self._headings_for(draft_type, count)
                ],
                "risks": self._recommendations("Risks", topic),
                "recommendations": self._recommendations("Recommendations", topic),
                "next_research_steps": ["Validate assumptions with current sources", "Compare alternatives", "Convert insights into an execution plan"],
                "sources": [],
            }
            if draft_type == "swot_report":
                content.update({
                    "strengths": self._bullets("Strengths", topic, agent_id),
                    "weaknesses": self._bullets("Weaknesses", topic, agent_id),
                    "opportunities": self._bullets("Opportunities", topic, agent_id),
                    "threats": self._bullets("Threats", topic, agent_id),
                })
            return content
        if draft_type in {"architecture_plan"}:
            return {
                **base,
                "system_goal": f"Define a reliable technical direction for {topic}.",
                "architecture_summary": f"{topic} should be structured around clear modules, data ownership, secure APIs, and deployable milestones.",
                "modules": [
                    {"name": name, "purpose": self._section_purpose(name, topic), "responsibilities": self._bullets(name, topic, agent_id)}
                    for name in ["Frontend Experience", "Backend API", "Data Layer", "Security", "Deployment"][:count]
                ],
                "apis": [{"name": "Core API", "purpose": f"Expose authenticated operations for {topic}", "methods": ["GET", "POST", "PATCH"]}],
                "database_design": [{"table": "projects", "purpose": "Track project context and progress"}, {"table": "files", "purpose": "Store document metadata and extracted context"}],
                "risks": self._recommendations("Risks", topic),
                "implementation_steps": self._recommendations("Implementation", topic),
            }
        if draft_type in {"content_calendar"}:
            return {
                **base,
                "platforms": ["LinkedIn", "Instagram", "YouTube"],
                "calendar_items": [
                    {"date": f"Day {index + 1}", "platform": "LinkedIn", "topic": item, "format": "Post", "owner": "Friday", "status": "Planned"}
                    for index, item in enumerate(self._bullets("Content Ideas", topic, agent_id)[:count])
                ],
            }
        if draft_type in {"study_plan"}:
            return {
                **base,
                "goal": f"Prepare effectively for {topic}.",
                "timeline": f"{count} focused study sessions",
                "topics": self._bullets("Topics", topic, agent_id),
                "daily_plan": [
                    {"day": f"Day {index + 1}", "focus": heading, "tasks": self._bullets(heading, topic, agent_id)[:3], "practice": ["Revise notes", "Self-test key concepts"]}
                    for index, heading in enumerate(self._headings_for(draft_type, count))
                ],
                "revision_schedule": ["Quick recap after each session", "Full review before final deadline"],
                "resources": ["Uploaded notes", "Relevant class material", "CEASER-generated summaries"],
            }
        if draft_type in {"execution_plan", "task_breakdown", "project_tracker", "workflow_plan", "learning_roadmap"}:
            milestones = [
                {"name": heading, "tasks": self._bullets(heading, topic, agent_id), "priority": "High" if index == 0 else "Medium", "deadline": f"Phase {index + 1}", "status": "Planned"}
                for index, heading in enumerate(self._headings_for(draft_type, count))
            ]
            return {
                **base,
                "objective": f"Move {topic} from idea to completed execution.",
                "project": topic,
                "workflow": topic,
                "milestones": milestones,
                "tasks": [task for milestone in milestones for task in milestone["tasks"][:2]],
                "owners": [agent_id],
                "dependencies": ["User review", "Available files and context"],
                "risks": self._recommendations("Risks", topic),
                "follow_ups": ["Review progress", "Resolve blockers", "Prepare next workflow"],
                "status_columns": ["Planned", "In Progress", "Review", "Completed"],
                "steps": self._recommendations("Steps", topic),
                "automations": [],
                "resources": ["CEASER memory", "Uploaded files", "User instructions"],
                "practice": [],
            }
        return {
            **base,
            "sections": [
                {"heading": heading, "summary": self._section_summary(heading, topic), "details": self._bullets(heading, topic, agent_id), "recommendations": self._recommendations(heading, topic)}
                for heading in self._headings_for(draft_type, count)
            ],
        }

    def _ensure_schema_keys(self, content: dict, schema: dict, *, prompt: str, title: str, agent_id: str) -> dict:
        topic = self._topic(prompt, title)
        for key, sample in schema.items():
            if key in content:
                continue
            if isinstance(sample, str):
                content[key] = self._schema_text(key, topic)
            elif isinstance(sample, list):
                content[key] = self._schema_list(key, topic, agent_id, sample)
            elif isinstance(sample, dict):
                content[key] = {"summary": self._schema_text(key, topic)}
            else:
                content[key] = None
        return content

    def _schema_list(self, key: str, topic: str, agent_id: str, sample: list) -> list:
        if sample and isinstance(sample[0], dict):
            template = sample[0]
            return [self._fill_object(template, key, topic, agent_id)]
        return self._bullets(key, topic, agent_id)

    def _fill_object(self, template: dict, key: str, topic: str, agent_id: str) -> dict:
        result = {}
        for field, sample in template.items():
            if isinstance(sample, str):
                result[field] = self._schema_text(field, topic)
            elif isinstance(sample, int):
                result[field] = 1
            elif isinstance(sample, list):
                result[field] = self._bullets(field, topic, agent_id)[:3]
            elif isinstance(sample, dict):
                result[field] = self._fill_object(sample, field, topic, agent_id)
            else:
                result[field] = None
        return result

    @staticmethod
    def _schema_text(key: str, topic: str) -> str:
        return f"{key.replace('_', ' ').title()} for {topic}."

    def _headings_for(self, draft_type: str, count: int) -> list[str]:
        defaults = {
            "business_plan": ["Executive Summary", "Problem", "Solution", "Market", "Business Model", "Go-To-Market", "Financial Plan"],
            "execution_plan": ["Objective", "Milestones", "Task Plan", "Timeline", "Risks", "Follow-Ups"],
            "study_plan": ["Foundation", "Core Concepts", "Practice", "Revision", "Mock Test", "Final Review"],
            "architecture_plan": ["Overview", "Modules", "APIs", "Data Model", "Security", "Deployment"],
            "research_report": ["Executive Summary", "Key Findings", "Market Signals", "Recommendations", "Sources"],
        }
        return (defaults.get(draft_type) or ["Overview", "Context", "Plan", "Risks", "Next Actions"])[:count]

    @staticmethod
    def _topic(prompt: str, title: str) -> str:
        return (prompt or title).strip().rstrip(".") or "this work"

    @staticmethod
    def _section_purpose(section: str, topic: str) -> str:
        return f"Explain the {section.lower()} clearly for {topic}."

    def _business_plan_sections(self, topic: str) -> list[dict]:
        subject = self._business_subject(topic)
        return [
            {
                "heading": "Executive Summary",
                "summary": f"{subject} is positioned as a healthtech platform that helps clinics, diagnostic centers, and patients manage digital health records more securely and efficiently.",
                "details": [
                    f"{subject} addresses fragmented medical records, manual follow-ups, repeated patient intake, and insecure sharing through consumer chat apps.",
                    "The product direction should focus on interoperable health records, clinic-ready workflows, consent-based sharing, and AI-assisted document organization.",
                    "The strongest early wedge is small and mid-sized clinics that need better continuity of care without buying a complex hospital management system.",
                    "The business should prove value through faster record retrieval, fewer administrative delays, better patient retention, and cleaner documentation.",
                ],
                "recommendations": [
                    "Launch with one focused clinic workflow before expanding into a broad healthcare operating platform.",
                    "Use pilot clinics in Hyderabad to validate onboarding, record sharing, and repeat usage.",
                    "Package the product around trust, speed, and interoperability instead of generic AI features.",
                ],
            },
            {
                "heading": "Problem",
                "summary": "Healthcare data for small clinics is still scattered across paper files, PDFs, WhatsApp messages, lab portals, and disconnected software.",
                "details": [
                    "Patients struggle to keep previous prescriptions, lab reports, scans, and discharge notes available when they visit a new doctor.",
                    "Clinics lose time searching for old records, asking repeated questions, and manually coordinating reports between patients and labs.",
                    "Sensitive medical data is often shared through informal channels, which creates privacy, security, and compliance risk.",
                    "Existing enterprise systems are often too heavy, expensive, or operationally complex for smaller clinics.",
                ],
                "recommendations": [
                    "Frame the pain as continuity of care plus operational efficiency, not only file storage.",
                    "Quantify the time lost per patient visit during pilot testing.",
                    "Prioritize secure sharing and patient consent as visible product differentiators.",
                ],
            },
            {
                "heading": "Solution",
                "summary": f"{subject} should provide a secure digital health record locker that lets patients and clinics store, organize, retrieve, and share medical records in one place.",
                "details": [
                    "Patients can upload prescriptions, reports, invoices, scans, and summaries into a structured health record timeline.",
                    "Clinics can access patient-authorized records quickly during consultation, reducing repeated intake and missing context.",
                    "AI can classify documents, extract key medical details, summarize long records, and surface relevant history before the visit.",
                    "Interoperability should be built through exportable records, structured metadata, and future integrations with clinic and lab systems.",
                ],
                "recommendations": [
                    "Build the first version around upload, OCR/extraction, timeline, sharing, and clinic access.",
                    "Keep AI assistive and explainable so doctors trust the output.",
                    "Design for low-friction adoption: mobile-first patient experience and simple clinic dashboard.",
                ],
            },
            {
                "heading": "Market",
                "summary": "India has a large and growing digital health opportunity driven by clinic digitization, rising patient expectations, telehealth habits, and demand for portable records.",
                "details": [
                    "The initial market can focus on independent clinics, specialty clinics, diagnostic centers, and chronic-care patients who repeatedly need historical records.",
                    "Urban and semi-urban markets are attractive because patients already use smartphones and clinics are under pressure to modernize operations.",
                    "Competitors may include health record apps, hospital systems, patient portals, and clinic management software, but many do not solve patient-owned interoperability well.",
                    "Hyderabad is a strong launch market because it has healthcare density, tech talent, and an active startup ecosystem.",
                ],
                "recommendations": [
                    "Start with one specialty segment such as dental, dermatology, diabetology, or diagnostics to sharpen messaging.",
                    "Create a competitor map covering health lockers, EMR platforms, and patient engagement tools.",
                    "Use pilots to identify the segment with the shortest sales cycle and strongest repeat usage.",
                ],
            },
            {
                "heading": "Business Model",
                "summary": f"{subject} can combine B2B clinic subscriptions with patient-side freemium access and paid premium storage or family health management features.",
                "details": [
                    "Clinics can pay a monthly subscription for patient record access, staff accounts, document organization, and workflow tools.",
                    "Patients can use a free health locker with limits, then upgrade for family profiles, larger storage, smart summaries, and priority sharing features.",
                    "Diagnostic labs and specialty clinics can become channel partners if the platform reduces report delivery friction.",
                    "Long-term revenue can expand into analytics, integrations, insurance workflows, and enterprise healthcare partnerships after trust is established.",
                ],
                "recommendations": [
                    "Validate willingness to pay from clinics before building advanced paid patient features.",
                    "Keep early pricing simple: free pilot, starter clinic plan, and growth clinic plan.",
                    "Avoid monetizing sensitive data; make privacy part of the business promise.",
                ],
            },
            {
                "heading": "Go-To-Market",
                "summary": "The launch should begin with clinic pilots, patient onboarding through doctors, and targeted founder-led sales in one city.",
                "details": [
                    "Acquire the first clinics through direct outreach, founder networks, medical associations, and local healthcare communities.",
                    "Use every pilot to capture measurable before/after outcomes: onboarding time, repeat visits, report retrieval, and patient satisfaction.",
                    "Create simple demo assets for doctors: one patient timeline, one report summary, one secure sharing flow.",
                    "Patient growth should come through clinic invitations, QR onboarding, referral loops, and family health record use cases.",
                ],
                "recommendations": [
                    "Run 5 to 10 pilot clinics before scaling marketing spend.",
                    "Build a case study from the strongest pilot and use it for the next wave of clinic acquisition.",
                    "Position the product as a practical digital record layer, not as a replacement for doctors or clinic software.",
                ],
            },
            {
                "heading": "Financial Plan",
                "summary": "The financial plan should focus on pilot validation, low customer acquisition cost, recurring clinic revenue, and disciplined product development.",
                "details": [
                    "Early costs will include product development, cloud storage, OCR/AI usage, security, compliance work, support, and founder-led sales.",
                    "The first revenue milestone should be paid clinic subscriptions from pilot conversions rather than broad consumer monetization.",
                    "Important metrics include active clinics, active patient records, records uploaded per month, monthly recurring revenue, churn, and support cost per clinic.",
                    "Unit economics improve if clinics invite patients repeatedly and document processing is optimized for predictable AI and storage costs.",
                ],
                "recommendations": [
                    "Set a 90-day goal: pilot clinics signed, paid conversions, monthly record volume, and retention.",
                    "Track AI and storage cost per active clinic from day one.",
                    "Raise funding only after proving clinic adoption and repeat patient usage.",
                ],
            },
        ]

    @staticmethod
    def _business_subject(topic: str) -> str:
        lowered = topic.lower()
        if "clinilocker" in lowered or "clini locker" in lowered:
            return "Clinilocker"
        cleaned = re.sub(r"^(create|make|generate|write)\s+(a\s+)?", "", topic, flags=re.I).strip()
        cleaned = re.sub(r"\b(business plan|pitch deck|report|document)\b", "", cleaned, flags=re.I).strip(" .:-")
        return cleaned.title() if cleaned else "The startup"

    def _section_summary(self, section: str, topic: str) -> str:
        subject = self._business_subject(topic)
        lower = section.lower()
        if "executive" in lower or "overview" in lower:
            return f"{subject} should be framed as a focused solution with a clear customer, painful problem, practical product, and measurable path to adoption."
        if "problem" in lower:
            return f"The core problem is fragmented workflows, scattered information, and avoidable manual effort around {subject.lower()}."
        if "solution" in lower or "product" in lower:
            return f"The solution should give users a simple, secure, and repeatable way to complete the job without switching between disconnected tools."
        if "market" in lower:
            return f"The market opportunity depends on choosing a narrow early segment, proving value quickly, and expanding after repeat usage is visible."
        if "business" in lower or "revenue" in lower:
            return f"The business model should start with a simple recurring plan and expand only after the first user segment proves strong retention."
        if "go-to-market" in lower or "launch" in lower:
            return f"The launch should start with founder-led pilots, clear proof points, and a repeatable acquisition motion."
        if "financial" in lower:
            return "The financial plan should protect runway while validating paid demand, acquisition cost, retention, and operating cost."
        return f"{section} defines the practical decisions needed to move {subject} forward."

    def _bullets(self, section: str, topic: str, agent_id: str) -> list[str]:
        subject = self._business_subject(topic)
        lower = section.lower()
        if "problem" in lower:
            return [
                f"{subject} should focus on a painful, frequent workflow that users already struggle to manage.",
                "The current alternatives are fragmented, manual, slow, or too expensive for the first target users.",
                "The problem should be measured through time lost, repeated work, missed information, and operational risk.",
                "The first demo should show the before-and-after workflow in less than two minutes.",
            ]
        if "solution" in lower or "product" in lower:
            return [
                f"{subject} should deliver one clear workflow that feels immediately useful to the target user.",
                "Core features should be simple enough for first-time users but strong enough to support repeat usage.",
                "AI should reduce work, summarize context, and guide decisions without hiding the source information.",
                "The product should earn trust through speed, clarity, privacy, and predictable results.",
            ]
        if "market" in lower:
            return [
                "Start with a narrow early market where the pain is obvious and buying decisions are reachable.",
                "Use pilots to learn who adopts fastest, who pays, and which use case creates repeated engagement.",
                "Map direct competitors, manual substitutes, and adjacent tools users already rely on.",
                "Expand only after the first segment produces case studies and repeatable sales motion.",
            ]
        if "business" in lower or "revenue" in lower:
            return [
                "Use a simple subscription model for the first paying customer segment.",
                "Tie pricing to clear value: time saved, better organization, reduced risk, or higher throughput.",
                "Track retention and usage before adding complex pricing tiers.",
                "Keep data privacy and trust as non-negotiable parts of the value proposition.",
            ]
        if "go-to-market" in lower or "launch" in lower:
            return [
                "Begin with founder-led outreach and high-touch onboarding for the first pilots.",
                "Turn the best pilot result into a case study, demo, and repeatable sales script.",
                "Use direct channels first before scaling paid marketing.",
                "Create a weekly feedback loop so product changes follow real user behavior.",
            ]
        if "financial" in lower:
            return [
                "Track monthly recurring revenue, activation, retention, gross margin, and support cost.",
                "Protect runway by avoiding broad feature expansion before paid demand is proven.",
                "Separate fixed product costs from variable AI, storage, and support costs.",
                "Set a 90-day financial milestone tied to paid pilots and usage growth.",
            ]
        return [
            f"{subject} needs a clear owner, measurable outcome, and practical next step for this section.",
            "Use real user behavior and available project context to decide what matters most.",
            "Convert assumptions into testable milestones instead of broad statements.",
            f"{agent_id.title()} should move this work toward a concrete deliverable the user can review.",
        ]

    def _recommendations(self, section: str, topic: str) -> list[str]:
        subject = self._business_subject(topic)
        lower = section.lower()
        if "problem" in lower:
            return ["Interview target users about the exact workflow pain.", "Measure the cost of the current manual process.", "Use the strongest pain point as the opening demo story."]
        if "solution" in lower or "product" in lower:
            return ["Build the smallest workflow that proves the value.", "Keep the first product path simple and repeatable.", "Use user feedback to decide the next feature, not assumptions."]
        if "market" in lower:
            return ["Choose one initial segment for launch.", "Create a competitor map before pitching.", "Use pilot evidence to refine positioning."]
        if "financial" in lower or "business" in lower or "revenue" in lower:
            return ["Validate paid demand before scaling costs.", "Track usage and retention weekly.", "Keep pricing simple for V1."]
        if "go-to-market" in lower or "launch" in lower:
            return ["Start with direct outreach.", "Convert pilots into case studies.", "Create a repeatable onboarding checklist."]
        return [f"Turn this section into one decision for {subject}.", "Define the next measurable milestone.", "Review the result before export."]

    @staticmethod
    def _visual(section: str, topic: str) -> str:
        return f"Use a clean visual that shows {section.lower()} for {topic}."

    @staticmethod
    def _speaker_notes(section: str, topic: str) -> str:
        return f"Talk through why {section.lower()} matters for {topic}, then close with the next decision."
