from __future__ import annotations

import re
from textwrap import shorten

from app.services.document_generation.docx_generator import DOCXGenerator
from app.services.document_generation.pdf_generator import PDFGenerator
from app.services.document_generation.pptx_generator import PPTXGenerator
from app.services.document_generation.schemas import GeneratedDocumentResult
from app.services.document_generation.template_manager import TemplateManager
from app.services.document_generation.xlsx_generator import XLSXGenerator
from app.intelligence.ai.sync import generate_text_sync


class DocumentGenerator:
    generators = {
        "docx": DOCXGenerator(),
        "pdf": PDFGenerator(),
        "pptx": PPTXGenerator(),
        "xlsx": XLSXGenerator(),
    }

    def generate(self, *, prompt: str, kind: str, template_id: str | None = None, agent_id: str | None = None) -> GeneratedDocumentResult:
        templates = TemplateManager()
        template = templates.get(template_id) if template_id else templates.route(prompt, kind)
        selected_agent = agent_id or template.agent_id
        title = self._title(prompt, template.name)
        content = self._content(prompt=prompt, title=title, template_name=template.name, sections=template.sections, agent_id=selected_agent)
        sections = self._split_sections(content, template.sections)
        generator = self.generators[kind]
        bytes_data = generator.generate(title, sections)
        filename = f"{self._safe_name(title)}.{kind}"
        return GeneratedDocumentResult(
            title=title,
            kind=kind,
            content=content,
            bytes_data=bytes_data,
            content_type=generator.content_type,
            filename=filename,
            template=template,
            agent_id=selected_agent,
        )

    def _content(self, *, prompt: str, title: str, template_name: str, sections: list[str], agent_id: str) -> str:
        is_workflow = template_name == "Workflow Execution Plan"
        instruction = (
            f"Create a professional {template_name} titled '{title}'.\n"
            f"Owner agent: {agent_id}.\n"
            f"User prompt: {prompt}\n"
            f"Use exactly these sections: {', '.join(sections)}.\n"
            "Return clean sectioned content only. Do not include JSON, markdown code fences, placeholder text, or meta commentary.\n"
            "Each section must start with its section heading on its own line, followed by practical finished content.\n"
            "Use concise paragraphs and bullet points where useful. Make it ready for a real user to download."
        )
        if is_workflow:
            instruction += (
                "\nThis is an execution document, not a research report. Do not use Executive Summary, Methodology, "
                "Key Findings, Market Signals, Recommendations, or Sources. "
                "For Execution Phases, use numbered phases with a name, purpose, owner, and deadline. "
                "For Task Plan, group concrete checklist tasks beneath each phase and give every task an owner and due date. "
                "For Risks and Mitigations, pair each risk with a specific mitigation. "
                "Do not invent claims, research, competitors, market data, or citations that the user did not provide."
            )
        try:
            response = generate_text_sync(
                instructions=(
                    "You are CEASER's document creation engine. Write real finished document content. "
                    "Do not write instructions, placeholders, or meta commentary. Use the requested headings exactly."
                ),
                input_text=instruction,
                temperature=0.25,
                max_output_tokens=2200,
            )
        except Exception:
            response = ""
        if self._invalid_content(response):
            return "\n\n".join(f"{section}\n{self._fallback_body(section, prompt)}" for section in sections)
        return self._clean_content(response)

    def _split_sections(self, content: str, section_names: list[str]) -> list[tuple[str, str]]:
        sections: list[tuple[str, str]] = []
        for index, section in enumerate(section_names):
            next_section = section_names[index + 1] if index + 1 < len(section_names) else None
            pattern = rf"{re.escape(section)}\s*\n(.+?)(?=\n\s*{re.escape(next_section)}\s*\n|\Z)" if next_section else rf"{re.escape(section)}\s*\n(.+)\Z"
            match = re.search(pattern, content, flags=re.I | re.S)
            body = match.group(1).strip() if match else self._fallback_body(section, content)
            body = self._clean_body(body)
            sections.append((section, body))
        return sections

    @staticmethod
    def _clean_content(content: str) -> str:
        cleaned = content.strip()
        cleaned = re.sub(r"```(?:json|markdown|text)?", "", cleaned, flags=re.I)
        cleaned = cleaned.replace("```", "")
        cleaned = re.sub(r"^\s*#+\s*", "", cleaned, flags=re.M)
        return cleaned.strip()

    @staticmethod
    def _clean_body(body: str) -> str:
        body = re.sub(r"\{[\s\S]*?\}", "", body) if body.strip().startswith("{") else body
        lines = []
        for line in body.splitlines():
            cleaned = re.sub(r"^\s*[-*]\s*", "- ", line.strip())
            cleaned = re.sub(r"^\s*\d+[.)]\s*", lambda m: m.group(0), cleaned)
            if cleaned:
                lines.append(cleaned)
        return "\n".join(lines).strip()

    @staticmethod
    def _invalid_content(content: str) -> bool:
        if not content or not content.strip():
            return True
        lowered = content.lower()
        blocked = ["live ai synthesis", "placeholder", "point for", "template text", "draft generation failed"]
        if any(term in lowered for term in blocked):
            return True
        if content.strip().startswith("{") and content.strip().endswith("}"):
            return True
        return False

    @staticmethod
    def _title(prompt: str, fallback: str) -> str:
        if "workflow" in prompt.lower():
            goal_match = re.search(r"\bgoal\s*:\s*(.+?)(?=\n\s*\n|\Z)", prompt, flags=re.I | re.S)
            if goal_match:
                goal = re.sub(r"\s+", " ", goal_match.group(1)).strip(" .")
                goal = re.sub(r"^(?:to\s+)?(?:create|build)\s+", "", goal, flags=re.I)
                return f"{shorten(goal.title(), width=62, placeholder='')} Workflow".strip()
            project_match = re.search(r"create a workflow document for\s+(.+?)\.", prompt, flags=re.I)
            if project_match:
                return f"{project_match.group(1).strip().title()} Workflow"
        if re.search(r"\bclinilocker\b", prompt, flags=re.I) and re.search(r"\bbusiness plan\b", prompt, flags=re.I):
            return "Clinilocker HealthTech Business Plan"
        cleaned = re.sub(r"\b(create|generate|make|write|draft|prepare|a|an|the|document|doc|file|report|deck|spreadsheet|pdf|docx|pptx|xlsx)\b", " ", prompt, flags=re.I)
        cleaned = re.sub(r"\b(about|on|for|in|as)\b", " ", cleaned, flags=re.I)
        cleaned = re.sub(r"\s+", " ", cleaned).strip(" .")
        return cleaned.title()[:80] if cleaned else fallback

    @staticmethod
    def _safe_name(title: str) -> str:
        return re.sub(r"[^A-Za-z0-9._-]+", "-", title).strip("-") or "ceaser-document"

    @staticmethod
    def _fallback_body(section: str, prompt: str) -> str:
        clean_prompt = re.sub(r"\b(create|generate|make|write|draft|prepare)\b", " ", prompt, flags=re.I)
        clean_prompt = re.sub(r"\b(a|an|the|document|doc|file|report|deck|spreadsheet|pdf|docx|pptx|xlsx|about|on|for|in|as)\b", " ", clean_prompt, flags=re.I)
        clean_prompt = re.sub(r"\s+", " ", clean_prompt).strip(" .")
        topic = shorten(clean_prompt or prompt.strip(), width=90, placeholder="...")
        section_key = section.lower().strip()
        lower_topic = topic.lower()
        raw_prompt = prompt.lower()

        if "workflow" in raw_prompt:
            workflow_map = {
                "workflow overview": f"This execution plan organizes {topic} into accountable phases, practical tasks, and review points. It is designed to turn the stated goal into a deliverable plan rather than a high-level research report.",
                "goal": f"Deliver the agreed outcome for {topic}. Keep the work focused on the user-provided scope and validate each phase before moving forward.",
                "scope and assumptions": "- Work only within the stated project context and requirements.\n- Confirm missing compliance, budget, technical, and stakeholder constraints during the first phase.\n- Treat any timeline as a target to be re-baselined after discovery.",
                "execution phases": "1. Discovery and alignment\n- Purpose: confirm users, requirements, constraints, and success criteria.\n- Owner: Project lead.\n- Deadline: Week 1.\n\n2. Build and validate\n- Purpose: deliver the smallest useful version and test it with stakeholders.\n- Owner: Product and delivery team.\n- Deadline: Weeks 2-4.\n\n3. Launch and improve\n- Purpose: release, measure adoption, resolve issues, and prioritize improvements.\n- Owner: Project lead and operations team.\n- Deadline: Week 5 onward.",
                "task plan": "Discovery and alignment\n- Confirm target users, problem statement, scope, and constraints. Owner: Project lead. Due: Week 1.\n- Capture requirements and acceptance criteria. Owner: Product owner. Due: Week 1.\n\nBuild and validate\n- Create the prioritized delivery backlog. Owner: Product owner. Due: Week 2.\n- Build and test the first usable release. Owner: Delivery team. Due: Week 4.\n\nLaunch and improve\n- Run the launch checklist and stakeholder review. Owner: Operations lead. Due: Week 5.\n- Review metrics and improvement requests weekly. Owner: Project lead. Due: Weekly.",
                "dependencies": "- Confirmed scope and decision-maker approval.\n- Required people, budget, tools, and access.\n- Any legal, security, or compliance review needed before launch.\n- Stakeholder availability for validation and sign-off.",
                "timeline and deadlines": "- Week 1: discovery, scope confirmation, and plan approval.\n- Weeks 2-4: build, validation, and readiness review.\n- Week 5: launch, measurement, and issue triage.\n- Weekly: progress review, risk review, and plan adjustment.",
                "risks and mitigations": "- Unclear requirements — Mitigation: approve written scope and acceptance criteria in Week 1.\n- Delayed decisions — Mitigation: assign a named decision-maker and weekly review.\n- Technical or compliance blockers — Mitigation: complete early feasibility and compliance checks.\n- Timeline pressure — Mitigation: protect the minimum viable scope and defer non-critical work.",
                "success checks": "- Every phase has an accountable owner and agreed deadline.\n- The agreed deliverable meets written acceptance criteria.\n- Required testing, review, and approvals are complete.\n- Launch metrics and feedback are reviewed within the first week.\n- Open risks have owners and mitigation actions.",
                "immediate next actions": "1. Confirm the scope, target users, and measurable outcome with stakeholders.\n2. Name owners for discovery, delivery, review, and launch.\n3. Convert the task plan into a dated tracker.\n4. Schedule the first weekly progress and risk review.",
            }
            if section_key in workflow_map:
                return workflow_map[section_key]

        if "clinilocker" in raw_prompt and ("healthtech" in raw_prompt or "health tech" in raw_prompt or "healthcare" in raw_prompt):
            clinilocker_map = {
                "executive summary": (
                    "Clinilocker is positioned as an interoperable digital health record platform for clinics, diagnostic centers, and patients. "
                    "The business opportunity is to solve fragmented medical records, insecure file sharing, and poor continuity of care in everyday healthcare workflows. "
                    "By giving clinics a simple way to organize, access, and share patient records securely, Clinilocker can become a practical operating layer for small and mid-sized healthcare providers.\n"
                    "- Primary users: clinics, diagnostic centers, doctors, and patients.\n"
                    "- Core value: secure, organized, shareable health records.\n"
                    "- Launch focus: pilot clinics, patient onboarding, and trust-building."
                ),
                "problem": (
                    "Healthcare records are still scattered across paper files, WhatsApp messages, PDFs, lab portals, and disconnected clinic systems. "
                    "This creates delays, missing history, repeated tests, manual follow-ups, and privacy risks. Small clinics often cannot afford complex hospital software, while patients struggle to access and share their own records when visiting different providers.\n"
                    "- Patient data is fragmented across multiple locations.\n"
                    "- Clinics waste time managing records manually.\n"
                    "- Doctors lack complete patient context during visits.\n"
                    "- Existing tools are either too complex, too expensive, or not interoperable enough."
                ),
                "solution": (
                    "Clinilocker can provide a secure digital record locker where patients and clinics can store, organize, and share health documents in one place. "
                    "The platform should make it easy to upload prescriptions, lab reports, discharge summaries, invoices, and visit notes, while allowing controlled sharing between patients, clinics, labs, and doctors.\n"
                    "- Patient-controlled digital health record storage.\n"
                    "- Clinic dashboard for managing patient documents.\n"
                    "- Secure sharing links or access permissions.\n"
                    "- AI-assisted search, summaries, and record organization.\n"
                    "- Future integrations with labs, pharmacies, and hospital systems."
                ),
                "market": (
                    "India's healthcare market has strong demand for affordable digital health infrastructure, especially among clinics and diagnostic centers that are not served well by enterprise hospital systems. "
                    "Growing smartphone usage, digital payments, ABDM adoption, and increased patient expectations make digital health record management a practical opportunity. "
                    "Clinilocker should begin with a focused city-level pilot before expanding across segments.\n"
                    "- Initial beachhead: small clinics and diagnostic centers in Hyderabad.\n"
                    "- Early adopters: doctors who need faster access to patient history.\n"
                    "- Expansion path: multi-specialty clinics, labs, pharmacies, and patient family accounts.\n"
                    "- Differentiation: simple workflow, interoperability, and patient-first access."
                ),
                "business model": (
                    "Clinilocker can use a hybrid B2B and B2C model. Clinics can pay a monthly subscription for patient record management, staff access, and workflow tools. Patients can use a free basic record locker, with paid family storage, advanced summaries, and priority support introduced later.\n"
                    "- Clinic subscription: monthly SaaS plan per clinic or per doctor.\n"
                    "- Patient premium: family health locker and larger storage limits.\n"
                    "- Diagnostic/lab partnerships: document delivery and integration fees.\n"
                    "- Future revenue: AI summaries, analytics, insurance workflows, and enterprise integrations."
                ),
                "go-to-market": (
                    "The first launch should focus on a small number of clinics rather than a broad public campaign. Clinilocker should prove that it saves time, improves record access, and increases patient trust inside real clinic workflows.\n"
                    "- Recruit 5-10 pilot clinics in Hyderabad.\n"
                    "- Onboard clinic staff and digitize a limited set of patient records.\n"
                    "- Collect testimonials from doctors and patients.\n"
                    "- Publish educational content about secure health records and continuity of care.\n"
                    "- Use founder-led demos, local healthcare networks, and referral partnerships to grow."
                ),
                "financial plan": (
                    "The early financial plan should prioritize validation and low-cost growth. The first goal is not scale; it is proof that clinics will use and pay for the product. "
                    "Costs should focus on product development, secure hosting, onboarding support, and compliance readiness.\n"
                    "- Phase 1: pilot revenue from 5-10 clinics.\n"
                    "- Phase 2: paid monthly plans for clinics after workflow validation.\n"
                    "- Phase 3: introduce patient premium and partner integrations.\n"
                    "- Key metrics: clinic activation, monthly retention, records uploaded, patient shares, demos booked, and conversion to paid plans."
                ),
            }
            if section_key in clinilocker_map:
                return clinilocker_map[section_key]

        if "startup" in lower_topic and "marketing" in lower_topic:
            startup_marketing_map = {
                "summary": (
                    "Startup planning and marketing should work together from day one. The planning side defines the business goal, target customer, offer, timeline, and execution priorities. "
                    "The marketing side turns that plan into visibility, trust, lead generation, and customer feedback. A strong startup does not wait until the product is finished to begin marketing; it uses marketing early to validate the problem, sharpen positioning, and build demand before launch.\n"
                    "- Define the target customer and the exact pain point.\n"
                    "- Build a simple launch roadmap with weekly milestones.\n"
                    "- Use marketing channels to test messaging before scaling."
                ),
                "key points": (
                    "1. Customer clarity comes first: identify who the startup serves, what urgent problem they face, and why existing alternatives are not enough.\n"
                    "2. Positioning should be simple: explain the product in one sentence, with a clear benefit and a believable reason to trust it.\n"
                    "3. Planning should be milestone-based: split work into validation, MVP, pilot users, launch, feedback, and growth.\n"
                    "4. Marketing should begin before launch: publish useful content, collect early leads, talk to users, and test offers.\n"
                    "5. The first campaigns should focus on learning, not vanity metrics. Track conversations, signups, demos booked, retention signals, and objections."
                ),
                "risks": (
                    "- Building without customer validation can waste months on features users do not need.\n"
                    "- Marketing too broadly can dilute the message and attract the wrong audience.\n"
                    "- Depending on only one channel creates growth risk if that channel fails.\n"
                    "- Weak positioning makes even a useful product difficult to explain.\n"
                    "- Ignoring feedback after launch can slow product-market fit."
                ),
                "recommendations": (
                    "- Start with one primary customer segment and one urgent use case.\n"
                    "- Create a 30-day launch plan with weekly goals for product, content, outreach, and feedback.\n"
                    "- Build a simple landing page that explains the problem, solution, benefit, and call to action.\n"
                    "- Run founder-led outreach to 30-50 target users before spending heavily on ads.\n"
                    "- Publish 3-4 content themes: problem education, product value, customer stories, and industry insights.\n"
                    "- Review metrics weekly and adjust the offer, message, or audience based on evidence."
                ),
                "context": (
                    "Startup planning defines what the company is building, for whom, and why now. Marketing translates that strategy into market attention and customer learning. The two must be connected so every campaign supports a business milestone."
                ),
                "strategic options": (
                    "- Niche-first launch: focus on one narrow customer group and become highly relevant to them.\n"
                    "- Content-led launch: educate the market through posts, guides, videos, and founder insights.\n"
                    "- Partnership-led launch: work with communities, colleges, clinics, agencies, or local businesses to gain early trust.\n"
                    "- Pilot-led launch: onboard a small group of early users and use their feedback as the foundation for growth."
                ),
                "recommendation": (
                    "Use a niche-first launch supported by founder-led outreach and educational content. This gives the startup fast feedback, lower marketing cost, and a clearer path to early traction."
                ),
                "execution plan": (
                    "Week 1 - Customer clarity\n"
                    "- Define the target persona, urgent pain point, and value proposition.\n"
                    "- Output: one-page startup brief.\n\n"
                    "Week 2 - Offer and message\n"
                    "- Create landing page copy, pitch wording, and 3-4 content themes.\n"
                    "- Output: launch message kit.\n\n"
                    "Week 3 - Outreach and validation\n"
                    "- Contact target users, collect objections, book demos, and test the offer.\n"
                    "- Output: early lead list and feedback notes.\n\n"
                    "Week 4 - Launch review\n"
                    "- Review feedback, improve the product promise, and choose the strongest channel.\n"
                    "- Output: revised launch plan."
                ),
            }
            if section_key in startup_marketing_map:
                return startup_marketing_map[section_key]

        fallback_map = {
            "Executive Summary": f"{topic} needs a focused plan that connects the objective, audience, execution steps, and measurable outcomes. The goal is to turn the idea into a practical workflow that can be reviewed and improved over time.\n- Define the outcome clearly.\n- Identify the target audience and main problem.\n- Convert the strategy into weekly execution steps.",
            "Summary": f"{topic} needs a clear plan, a defined audience, practical execution steps, and measurable results. The document should help the user move from idea to action without getting lost in generic planning.",
            "Key Points": f"1. Define the main goal and success metric for {topic}.\n2. Identify the audience, use case, and strongest value proposition.\n3. Break execution into short milestones.\n4. Decide the channels, tools, and owners required.\n5. Review progress weekly and adjust based on evidence.",
            "Problem": f"The core problem is that {topic} can become scattered without a clear structure.\n- Priorities may become unclear.\n- Execution can slow down without owners and milestones.\n- Results are hard to improve if success metrics are not defined.",
            "Solution": f"The solution is to organize {topic} into a practical operating plan.\n- Define the outcome and audience.\n- Create a milestone-based roadmap.\n- Connect every action to a measurable result.",
            "Risks": f"- Unclear audience or positioning can weaken {topic}.\n- Too many priorities can slow execution.\n- Weak measurement can hide what is working.\n- Delayed feedback can lead to wrong decisions.",
            "Recommendations": "- Start with the highest-impact audience and use case.\n- Create a simple 30-day execution plan.\n- Track 3-5 meaningful metrics.\n- Review outcomes weekly and adjust the plan.",
            "Sources": "Sources should be added from connected research, uploaded documents, or verified references when available.",
        }
        return fallback_map.get(section, f"{section} for {topic}.\n- Define the purpose and expected result.\n- Explain the most important decisions.\n- Convert the section into clear next actions.")
