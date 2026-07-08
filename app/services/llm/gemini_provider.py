from __future__ import annotations

import re

import httpx

from app.core.config.settings import settings
from app.services.llm.config import LLMConfig, llm_config
from app.services.llm.provider import LLMProvider


class GeminiProvider(LLMProvider):
    def __init__(self, config: LLMConfig | None = None):
        self.config = config or llm_config

    def generate_response(self, message: str, context: dict) -> str:
        if not settings.gemini_api_key:
            return self._missing_key_response(context)

        prompt = self._build_prompt(message=message, context=context)
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.config.model}:generateContent"
        payload = {
            "contents": [{"role": "user", "parts": [{"text": prompt}]}],
            "generationConfig": {
                "temperature": self.config.temperature,
                "maxOutputTokens": self.config.max_tokens,
                "thinkingConfig": {"thinkingBudget": 0},
            },
        }
        try:
            with httpx.Client(timeout=30) as client:
                response = client.post(url, params={"key": settings.gemini_api_key}, json=payload)
                response.raise_for_status()
                data = response.json()
            return self._clean_response(self._extract_text(data), has_research=bool(context.get("research_result")))
        except httpx.HTTPError:
            return self._provider_error_response(context)

    def _build_prompt(self, message: str, context: dict) -> str:
        if context.get("structured_draft_json"):
            return message
        merged = context.get("merged_contributions", {})
        research = context.get("research_result")
        answer_mode = self._answer_mode(message, context)
        sections = [
            "You are CEASER, a Personal Intelligence Operating System.",
            "Synthesize the user request using CEASER context, memories, conversation, and specialist agent contributions.",
            "Choose the answer format from the user's intent. Never force every answer into Executive Summary, Key Trends, Insights, and Recommendations.",
            f"Detected answer mode: {answer_mode}.",
            self._format_instruction(answer_mode),
            "Do not claim to execute code, use browser control, generate documents, or control integrations unless the provided context is explicitly for document analysis.",
            "Do not expose internal orchestration details in the final answer.",
            "Do not say you selected agents, applied frameworks, used system context, used memory context, or coordinated specialists.",
            "Do not mention confidence scores, framework names, selected agents, contribution summaries, or internal scope names unless the user explicitly asks for those details.",
            "If the user asks for top startups, a startup list, or top companies, provide named companies/startups. Do not answer with startup categories.",
            "If the requested founding year cannot be verified from the provided sources, say that clearly and label the list as relevant 2026 healthtech startups rather than pretending exact founding dates are confirmed.",
            "For simple list questions, answer directly using your general knowledge plus any provided sources. Do not refuse just because live sources are directories, rankings, or incomplete.",
            "Write as a polished user-facing answer, not a debug report.",
            f"User message: {message}",
            f"CEASER scope: {context.get('scope', {})}",
            f"Memories: {context.get('memories', [])}",
            f"Conversation: {context.get('conversation', [])}",
            f"Projects: {context.get('projects', [])}",
            f"Attached documents: {context.get('documents', [])}",
            f"Agent contributions: {merged.get('contributions', [])}",
        ]
        if research:
            sections.append(f"Research result with sources: {research}")
            sections.append(
                "If research_result contains sources, synthesize the actual findings from source titles and snippets. "
                "Do not say only that resources were gathered. If research_result has zero sources, clearly say no reliable "
                "live web sources were found and separate that from what CEASER knows from memory."
            )
            sections.append(
                "For research answers, write a useful brief with concrete points, trends, companies, dates, or facts found "
                "in the research context. Include compact inline citations like [1], [2] when using source-backed claims. "
                "Do not put raw URLs in the answer because the UI shows source cards separately. "
                "When sources are broad directories or rankings, extract the most useful company names from source titles/snippets if available; "
                "if names are not available in the context, use general knowledge to provide a helpful provisional list and clearly note that source cards should be opened for verification."
            )
        sections.append(
            "Return only the final user-facing answer. Do not include a raw Sources section, source bibliography, "
            "debug trace, selected agent list, confidence scores, or JSON. The CEASER UI renders sources, citations, "
            "agent contributions, frameworks, and confidence separately. If research is present, cite compactly inline "
            "with bracket numbers like [1] where useful, but do not list the sources. Start directly with the answer; "
            "do not preface it with what CEASER did internally."
        )
        return "\n\n".join(sections)

    def _answer_mode(self, message: str, context: dict) -> str:
        normalized = message.lower()
        if context.get("document_generation"):
            return "document_generation"
        if any(term in normalized for term in ["study plan", "timetable", "time table", "revision plan", "exam plan", "prepare for exam"]):
            return "study_timetable"
        if any(term in normalized for term in ["job application", "resume", "cover letter", "interview", "sde", "software development engineer", "apply for"]):
            return "career_prep"
        if any(term in normalized for term in ["create a document", "write a document", "create document", "draft a document"]):
            return "document_draft"
        if any(term in normalized for term in ["business plan", "pitch deck", "proposal", "report", "project plan"]):
            return "structured_work"
        if normalized.strip().endswith("?") or any(normalized.startswith(prefix) for prefix in ["what ", "who ", "why ", "how ", "when ", "where ", "which "]):
            return "direct_answer"
        if any(term in normalized for term in ["plan", "steps", "roadmap", "schedule"]):
            return "action_plan"
        if context.get("research_result") or any(term in normalized for term in ["research", "sources", "latest", "news", "market", "competitor", "trends", "web"]):
            return "research_brief"
        return "natural_answer"

    def _format_instruction(self, mode: str) -> str:
        instructions = {
            "study_timetable": (
                "For study plans, return a practical timetable. Use a markdown table with columns: Day, Focus, What to Study, Practice, Output. "
                "After the table, add only a short daily routine and 3 exam tips. Do not use Key Trends or generic research sections."
            ),
            "career_prep": (
                "For job applications, return direct career preparation help. Use sections: Target Role, Skills to Prepare, Resume Checklist, "
                "Project/Portfolio Ideas, Interview Prep, Next 7 Days. Do not use Key Trends unless the user asks for industry research."
            ),
            "document_draft": (
                "For document creation, write the actual document content or a ready-to-edit draft. Use natural headings based on the requested document. "
                "Do not describe what should be written; write it."
            ),
            "structured_work": (
                "For business plans, pitch decks, reports, and proposals, produce the actual structured content with domain-specific details. "
                "Use headings that match the deliverable, not a generic research template."
            ),
            "research_brief": (
                "For research, use a concise research brief with: Title, Summary, Findings, Useful Signals, What To Do Next. "
                "Include compact inline citations like [1], [2] when source-backed. Do not list raw URLs."
            ),
            "direct_answer": (
                "For direct questions, answer directly first in 1-3 paragraphs. Add bullets only if they make the answer clearer. "
                "Do not use Executive Summary, Key Trends, or Recommendations."
            ),
            "action_plan": (
                "For plans and roadmaps, return a clear action plan with phases, tasks, timeline, and deliverables. Use a table when time-based. "
                "Do not use research-report sections unless research was requested."
            ),
            "document_generation": (
                "For document generation, provide polished document-ready prose. The content should be usable directly in DOCX/PDF/PPTX, not meta instructions."
            ),
            "natural_answer": (
                "Use the most natural format for the request. Start with the answer. Keep it concise and useful."
            ),
        }
        return instructions.get(mode, instructions["natural_answer"])

    def _extract_text(self, data: dict) -> str:
        candidates = data.get("candidates", [])
        if not candidates:
            return "Gemini returned no response candidates."
        parts = candidates[0].get("content", {}).get("parts", [])
        return "\n".join(part.get("text", "") for part in parts if part.get("text")).strip()

    def _missing_key_response(self, context: dict) -> str:
        return self._fallback_user_response(context, "Live AI synthesis is not available because the Gemini key is missing.")

    def _provider_error_response(self, context: dict) -> str:
        return self._fallback_user_response(context, "Live AI synthesis was temporarily unavailable, so this answer is based on retrieved sources and CEASER context.")

    def _fallback_user_response(self, context: dict, note: str) -> str:
        research = context.get("research_result") or {}
        sources = research.get("sources") or []
        memories = context.get("memories") or []
        conversation = context.get("conversation") or []
        last_user_message = ""
        for item in reversed(conversation):
            if item.get("role") == "user":
                last_user_message = item.get("content", "")
                break
        mode = self._answer_mode(context.get("current_message") or last_user_message, context)

        if mode == "study_timetable":
            return "\n".join([
                "10-Day Study Timetable",
                "",
                "| Day | Focus | What to Study | Practice | Output |",
                "| --- | --- | --- | --- | --- |",
                "| 1 | Arrays and Strings | Two pointers, sliding window, prefix sums | 4 problems | Pattern notes |",
                "| 2 | Linked Lists, Stack, Queue | Reversal, fast/slow pointer, monotonic stack | 4 problems | Mistake list |",
                "| 3 | Trees | DFS, BFS, BST basics | 4 problems | Traversal templates |",
                "| 4 | Graphs | BFS, DFS, shortest path basics | 3 problems | Graph checklist |",
                "| 5 | Recursion and Backtracking | Subsets, permutations, decision trees | 3 problems | Backtracking template |",
                "| 6 | Dynamic Programming | 1D DP, memoization, tabulation | 3 problems | DP patterns |",
                "| 7 | SQL and Databases | Joins, indexes, transactions | 10 SQL queries | SQL cheat sheet |",
                "| 8 | System Design Basics | APIs, caching, queues, databases | Design URL shortener | One-page design |",
                "| 9 | Resume and Projects | Rewrite bullets, prepare project stories | 1 mock interview | Final resume bullets |",
                "| 10 | Mock Day | Mixed revision and behavioral prep | 1 full mock | Final weak-area list |",
                "",
                "Daily routine: 60 minutes concepts, 90 minutes coding, 30 minutes review.",
            ])

        if mode == "career_prep":
            role = self._career_role(context.get("current_message") or last_user_message)
            return "\n".join([
                f"{role} Job Application Plan",
                "",
                f"Target Role: {role}.",
                "",
                "Skills to prepare:",
                *[f"- {item}" for item in self._career_skills(role)],
                "",
                "Resume checklist:",
                *[f"- {item}" for item in self._career_resume_checks(role)],
                "",
                "Next 7 days:",
                *[f"{index}. {item}" for index, item in enumerate(self._career_next_steps(role), start=1)],
            ])

        if mode == "document_draft":
            topic = self._document_topic(context.get("current_message") or last_user_message)
            return "\n".join([
                f"{topic} Document",
                "",
                "Purpose",
                f"This document gives a practical, ready-to-edit plan for {topic.lower()}. It is designed to clarify the goal, organize the work, and turn the idea into specific actions.",
                "",
                "Overview",
                f"{topic} should connect the core objective, target audience, execution steps, and success measures. The document should be used as a living plan that can be updated as new information appears.",
                "",
                "Key Sections",
                "1. Goal: Define the outcome and why it matters.",
                "2. Audience: Identify who this is for and what they need.",
                "3. Strategy: Explain the approach and positioning.",
                "4. Execution Plan: Break the work into clear phases and owners.",
                "5. Marketing Plan: Define channels, messages, and campaign ideas.",
                "6. Metrics: Track progress with simple measurable indicators.",
                "",
                "Execution Table",
                "| Phase | Focus | Actions | Output |",
                "| --- | --- | --- | --- |",
                "| 1 | Foundation | Clarify goals, audience, and offer | One-page project brief |",
                "| 2 | Planning | Build roadmap, timeline, and responsibilities | Execution calendar |",
                "| 3 | Marketing | Create message, content themes, and launch channels | Campaign plan |",
                "| 4 | Launch | Publish, test, collect feedback, and improve | Launch report |",
                "",
                "Next Steps",
                "- Convert this into a detailed project brief.",
                "- Add dates, owners, and priority levels.",
                "- Attach files or research sources if you want CEASER to make it more specific.",
            ])

        if mode == "structured_work":
            topic = self._document_topic(context.get("current_message") or last_user_message)
            return "\n".join([
                f"{topic} Plan",
                "",
                "Executive Summary",
                f"This plan defines how to move {topic.lower()} from idea to execution. It focuses on the problem, audience, solution, market direction, operating model, and next actions.",
                "",
                "Problem",
                "The project needs a clear execution structure so decisions, marketing, operations, and milestones do not remain scattered.",
                "",
                "Solution",
                "Use a focused plan that links strategy, execution tasks, marketing channels, and measurable outcomes in one workflow.",
                "",
                "Action Plan",
                "| Area | What To Do | Output |",
                "| --- | --- | --- |",
                "| Strategy | Define audience, offer, positioning, and goals | Strategy brief |",
                "| Marketing | Create content themes, channel plan, and launch messages | Marketing calendar |",
                "| Execution | Break work into weekly milestones | Roadmap |",
                "| Measurement | Track reach, leads, feedback, and conversions | Progress dashboard |",
                "",
                "Immediate Next Actions",
                "1. Finalize the exact audience.",
                "2. Write the one-line value proposition.",
                "3. Choose 2-3 marketing channels.",
                "4. Create a 14-day execution calendar.",
            ])

        if mode == "action_plan":
            workflow = (context.get("merged_contributions") or {}).get("workflow_response") or ""
            topic = self._document_topic(context.get("current_message") or last_user_message)
            lines = [
                "Execution Workflow",
                "",
                "Goal",
                f"Turn {topic.lower()} into a clear sequence of actions, owners, and outputs.",
                "",
                "Roadmap",
                "| Phase | Focus | Actions | Output |",
                "| --- | --- | --- | --- |",
                "| 1 | Clarify | Define the goal, audience, constraints, and success criteria | Project brief |",
                "| 2 | Plan | Break the work into milestones, priorities, and owners | Execution roadmap |",
                "| 3 | Build | Complete the core tasks and review progress every day | Working output |",
                "| 4 | Review | Check quality, risks, and next decisions | Final action list |",
                "",
                "Next Actions",
                "1. Write the exact outcome you want.",
                "2. List the tasks needed to reach it.",
                "3. Assign each task to an owner or CEASER agent.",
                "4. Review progress at the end of each day.",
            ]
            if workflow:
                lines.extend(["", "CEASER Workflow Context", workflow[:800]])
            return "\n".join(lines)

        title = "Research Brief" if sources else "CEASER Brief"
        lines = [title, "", "Executive Summary"]
        if sources:
            lines.append(f"{note} I found {len(sources)} relevant web sources and summarized the strongest signals below.")
        elif memories:
            lines.append(f"{note} I did not find live web sources, so I used relevant CEASER memory to answer.")
        else:
            lines.append(f"{note} I did not find enough live source context for a reliable research summary.")

        if sources:
            lines.extend(["", "Key Findings"])
            for index, source in enumerate(sources[:5], start=1):
                snippet = source.get("snippet") or source.get("title") or "Relevant source identified."
                lines.append(f"{index}. {snippet}")

            lines.extend(["", "Recommendations"])
            lines.append("Use the source cards below to verify details, then narrow the next question by geography, market segment, competitor set, or implementation angle.")
            lines.extend(["", "Sources"])
            lines.append("The source cards below include names, explanations, and links.")
            return "\n".join(lines)

        if memories:
            lines.extend(["", "Key Findings"])
            for index, memory in enumerate(memories[:3], start=1):
                lines.append(f"{index}. CEASER has relevant context that can personalize the answer.")
        return "\n".join(lines)

    def _document_topic(self, message: str) -> str:
        normalized = message.strip().rstrip(".")
        patterns = [
            r"(?:create|write|draft|generate|make|prepare)\s+(?:a|an)?\s*(?:document|doc|plan|report|brief)?\s*(?:about|on|for)?\s*(.+)",
            r"(?:document|plan|report|brief)\s+(?:about|on|for)\s+(.+)",
        ]
        for pattern in patterns:
            match = re.search(pattern, normalized, re.IGNORECASE)
            if match:
                topic = re.sub(r"\s+", " ", match.group(1)).strip(" .")
                if topic:
                    return topic[:1].upper() + topic[1:]
        return "Project Planning"

    def _career_role(self, message: str) -> str:
        normalized = message.strip().rstrip(".")
        patterns = [
            r"job application for\s+(.+)",
            r"apply for\s+(.+)",
            r"prepare.*?for\s+(.+)",
        ]
        for pattern in patterns:
            match = re.search(pattern, normalized, re.IGNORECASE)
            if match:
                role = match.group(1).strip()
                role = re.sub(r"\bin\b.+$", "", role, flags=re.IGNORECASE).strip()
                role = re.sub(r"\bat\b.+$", "", role, flags=re.IGNORECASE).strip()
                if role:
                    return role[:1].upper() + role[1:]
        return "Target Role"

    def _career_skills(self, role: str) -> list[str]:
        lower = role.lower()
        if any(term in lower for term in ["animator", "animation", "vfx", "visual effects"]):
            return [
                "Strong showreel with your best 30-60 seconds first",
                "Animation principles: timing, spacing, weight, arcs, anticipation, and acting",
                "VFX pipeline basics: modeling, rigging, layout, animation, lighting, compositing, and rendering",
                "Tools relevant to the studio: Maya, Blender, Houdini, Nuke, After Effects, Unreal, or equivalent",
                "Shot breakdowns that explain your exact contribution clearly",
            ]
        if any(term in lower for term in ["designer", "ui", "ux", "graphic"]):
            return [
                "Portfolio with 3-5 strong case studies",
                "Visual hierarchy, typography, spacing, color, and interaction basics",
                "Figma or equivalent design tooling",
                "Problem framing, user flows, and design rationale",
                "Clear presentation of process and final outcomes",
            ]
        if any(term in lower for term in ["software", "developer", "engineer", "sde", "programmer"]):
            return [
                "Data structures and algorithms",
                "One strong programming language such as Java, Python, C++, or JavaScript",
                "OOP, Git, SQL, REST APIs, debugging, and basic system design",
                "Two strong projects with clear technical impact",
            ]
        return [
            "Role-specific portfolio or proof of work",
            "Core tools and workflows used by employers in this role",
            "Clear examples of past work, results, and responsibilities",
            "Communication, collaboration, and problem-solving examples",
        ]

    def _career_resume_checks(self, role: str) -> list[str]:
        lower = role.lower()
        if any(term in lower for term in ["animator", "animation", "vfx", "visual effects"]):
            return [
                "Put your showreel link at the top of the resume.",
                "Add a short shot breakdown sheet explaining software used and your contribution.",
                "List studio-relevant tools like Maya, Blender, Houdini, Nuke, After Effects, Unreal, or Substance if applicable.",
                "Use project bullets such as 'animated character performance shot', 'created FX simulation', or 'composited final sequence'.",
                "Keep the resume to one page unless you already have strong studio experience.",
            ]
        if any(term in lower for term in ["software", "developer", "engineer", "sde", "programmer"]):
            return [
                "Put 2-3 strong projects with measurable outcomes.",
                "Mention tech stack clearly.",
                "Convert responsibilities into impact bullets.",
                "Add GitHub, portfolio, or deployed links where possible.",
            ]
        return [
            "Tailor the headline and summary to the exact role.",
            "Show proof of work near the top.",
            "Use outcome-focused bullets instead of generic responsibilities.",
            "Include only skills that are relevant to the target role.",
        ]

    def _career_next_steps(self, role: str) -> list[str]:
        lower = role.lower()
        if any(term in lower for term in ["animator", "animation", "vfx", "visual effects"]):
            return [
                "Select your best 6-8 shots and cut a 45-60 second showreel.",
                "Create a shot breakdown PDF with role, tools, and contribution for each shot.",
                "Update resume headline to match Animator / VFX Studio roles.",
                "Prepare a short portfolio email template for studios.",
                "Apply to 10-15 studios with customized showreel, resume, and breakdown sheet.",
                "Practice explaining 3 shots: challenge, process, tools, and final result.",
                "Make a tracker for studios applied, contact person, date, and follow-up status.",
            ]
        if any(term in lower for term in ["software", "developer", "engineer", "sde", "programmer"]):
            return [
                "Finalize resume.",
                "Prepare 2 project explanations.",
                "Solve 20 high-frequency DSA problems.",
                "Practice 1 mock interview.",
                "Apply to 15-20 targeted roles.",
            ]
        return [
            "Finalize resume for the target role.",
            "Prepare portfolio or proof-of-work links.",
            "Write a short customized cover note.",
            "Apply to 10-15 relevant openings.",
            "Track follow-ups and prepare interview answers.",
        ]

    def _clean_response(self, response: str, has_research: bool) -> str:
        if not has_research:
            return response
        markers = ["\n---\n**Sources:**", "\n**Sources:**", "\n### Sources", "\nSources:"]
        cleaned = response
        for marker in markers:
            if marker in cleaned:
                cleaned = cleaned.split(marker, 1)[0].strip()
        return cleaned
