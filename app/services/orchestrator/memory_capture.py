from __future__ import annotations

import re

from sqlalchemy.orm import Session

from app.repositories.memory_repository import MemoryRepository


class MemoryCapture:
    def __init__(self, db: Session):
        self.db = db
        self.memories = MemoryRepository(db)

    def capture(self, user_id: str, message: str) -> list[dict]:
        candidates = self.extract_candidates(message)
        general_candidates = self.extract_general_candidates(message)
        if candidates:
            general_candidates = [candidate for candidate in general_candidates if not candidate["content"].startswith("Recent request:")]
        candidates.extend(general_candidates)
        return self._store_candidates(user_id=user_id, candidates=candidates)

    def capture_interaction(self, user_id: str, user_message: str, assistant_response: str) -> list[dict]:
        candidates = self.extract_response_candidates(user_message=user_message, assistant_response=assistant_response)
        return self._store_candidates(user_id=user_id, candidates=candidates)

    def _store_candidates(self, user_id: str, candidates: list[dict]) -> list[dict]:
        stored = []
        for candidate in candidates:
            existing = self.memories.find_exact(
                user_id=user_id,
                memory_type=candidate["memory_type"],
                content=candidate["content"],
            )
            if existing:
                continue
            memory = self.memories.create(
                user_id=user_id,
                memory_type=candidate["memory_type"],
                content=candidate["content"],
                metadata={
                    "confidence_score": candidate["confidence_score"],
                    "source": "ceaser_orchestrator",
                },
            )
            stored.append(
                {
                    "id": memory.id,
                    "memory_type": memory.memory_type,
                    "content": memory.content,
                    "confidence_score": candidate["confidence_score"],
                }
            )
        if stored:
            self.db.commit()
        return stored

    def extract_candidates(self, message: str) -> list[dict]:
        rules = [
            (r"\bmy startup is called ([A-Za-z0-9 _-]+)", "project", "Startup name is {value}", 0.9),
            (r"\bstartup is called ([A-Za-z0-9 _-]+)", "project", "Startup name is {value}", 0.85),
            (r"\bmy project is called ([A-Za-z0-9 _-]+)", "project", "Project name is {value}", 0.85),
            (r"\b(?:my|our|the)\s+co[- ]founder is ([A-Za-z0-9 _-]+?)(?:,| and |\.\s*|$)", "project", "Co-founder is {value}", 0.88),
            (r"\btogether\s+you\s+are\s+building\s+(.+?)(?:\.|$)", "project", "Building {value}", 0.84),
            (r"\bwe(?:'re| are)\s+building\s+(.+?)(?:\.|$)", "project", "Building {value}", 0.84),
            (r"\b(?:we\s+)?plan\s+to\s+launch\s+in\s+([A-Za-z0-9 _-]+)", "project", "Launch location is {value}", 0.84),
            (r"\bplan is to launch in ([A-Za-z0-9 _-]+)", "project", "Launch location is {value}", 0.84),
            (r"\bremember that (.+)", "conversation", "{value}", 0.75),
            (r"\bwe decided to (.+)", "decision", "Decision: {value}", 0.8),
            (r"\bmy goal is (.+)", "goal", "Goal: {value}", 0.8),
        ]
        candidates = []
        for pattern, memory_type, template, confidence in rules:
            match = re.search(pattern, message, flags=re.IGNORECASE)
            if match:
                value = match.group(1).strip().rstrip(".")
                candidates.append(
                    {
                        "memory_type": memory_type,
                        "content": template.format(value=value),
                        "confidence_score": confidence,
                    }
                )
        unique: dict[tuple[str, str], dict] = {}
        for candidate in candidates:
            key = (candidate["memory_type"], candidate["content"].lower())
            if key not in unique or candidate["confidence_score"] > unique[key]["confidence_score"]:
                unique[key] = candidate
        return list(unique.values())

    def extract_general_candidates(self, message: str) -> list[dict]:
        normalized = message.strip()
        if not normalized or len(normalized) < 8:
            return []

        rules = [
            (r"\bmy name is ([A-Za-z][A-Za-z0-9 _.-]+)", "conversation", "User name is {value}", 0.9),
            (r"\buser is CEASER founder\b", "conversation", "User is CEASER founder", 0.95),
            (r"\bi (?:am|'m) your founder\b", "conversation", "User is CEASER founder", 0.95),
            (r"\bi am ([A-Za-z][A-Za-z0-9 _.,&/-]+)", "conversation", "User is {value}", 0.72),
            (r"\bi'm ([A-Za-z][A-Za-z0-9 _.,&/-]+)", "conversation", "User is {value}", 0.72),
            (r"\bmy (?:preferred|favorite|favourite) ([A-Za-z0-9 _-]+) is ([A-Za-z0-9 _.,&/-]+)", "conversation", "User preferred {key} is {value}", 0.82),
            (r"\bi (?:prefer|like|use) ([A-Za-z0-9 _.,&/-]+)", "conversation", "User preference: {value}", 0.68),
            (r"\bi (?:study|am studying|learn|am learning) ([A-Za-z0-9 _.,&/-]+)", "goal", "Learning focus: {value}", 0.76),
            (r"\bi want to (?:become|learn|prepare for|build) ([A-Za-z0-9 _.,&/-]+)", "goal", "Goal: {value}", 0.8),
            (r"\bi have (?:an? )?(exam|test|interview|meeting|demo|presentation) (?:on|at|tomorrow|today|in)?\s*(.*)", "goal", "Upcoming {key}: {value}", 0.78),
            (r"\b(?:create|prepare|make|build|generate) (?:a |an )?(study plan|business plan|pitch deck|report|document|timetable|time table|resume|cover letter|job application)(?: for)?\s*(.*)", "conversation", "Requested {key}: {value}", 0.66),
        ]

        candidates = []
        for pattern, memory_type, template, confidence in rules:
            match = re.search(pattern, normalized, flags=re.IGNORECASE)
            if not match:
                continue
            groups = [group.strip().rstrip(".") for group in match.groups()]
            if "{key}" in template and len(groups) >= 2:
                key, value = groups[0], groups[1] or groups[0]
                content = template.format(key=key, value=value)
            else:
                value = groups[-1] if groups else normalized
                content = template.format(value=value)
            if content.lower().startswith("user is your founder"):
                continue
            if self._is_low_value_content(content):
                continue
            candidates.append({"memory_type": memory_type, "content": content, "confidence_score": confidence})

        if self._looks_like_meaningful_request(normalized):
            candidates.append(
                {
                    "memory_type": "conversation",
                    "content": f"Recent request: {normalized[:220]}",
                    "confidence_score": 0.55,
                }
            )

        return self._unique(candidates)

    def extract_response_candidates(self, user_message: str, assistant_response: str) -> list[dict]:
        user = user_message.strip()
        response = assistant_response.strip()
        if not user or not response:
            return []
        lower_user = user.lower()
        lower_response = response.lower()
        title = response.splitlines()[0].replace("#", "").strip()[:90] or "CEASER response"

        candidates: list[dict] = []
        if any(term in lower_user for term in ["study plan", "timetable", "time table", "exam", "revision"]):
            candidates.append({"memory_type": "goal", "content": f"Generated study plan: {title}", "confidence_score": 0.78})
        if any(term in lower_user for term in ["job application", "resume", "cover letter", "interview", "portfolio"]):
            candidates.append({"memory_type": "conversation", "content": f"Prepared career material: {title}", "confidence_score": 0.76})
        if any(term in lower_user for term in ["business plan", "pitch deck", "proposal", "report", "document"]):
            candidates.append({"memory_type": "project", "content": f"Generated project document: {title}", "confidence_score": 0.76})
        if any(term in lower_user for term in ["research", "sources", "market", "competitor", "news"]) or "sources" in lower_response:
            candidates.append({"memory_type": "research", "content": f"Research completed: {title}", "confidence_score": 0.74})
        if any(term in lower_response for term in ["next 7 days", "next steps", "action plan", "daily routine"]):
            candidates.append({"memory_type": "decision", "content": f"Action plan created: {title}", "confidence_score": 0.68})
        return self._unique(candidates)

    def _looks_like_meaningful_request(self, message: str) -> bool:
        if len(message) < 18 or len(message) > 260:
            return False
        return bool(
            re.search(
                r"\b(create|prepare|make|build|generate|plan|remember|study|research|draft|write|apply|learn|goal|project|startup)\b",
                message,
                flags=re.IGNORECASE,
            )
        )

    def _is_low_value_content(self, content: str) -> bool:
        value = content.split(":", 1)[-1].strip() if ":" in content else content
        return len(value) < 3 or value.lower() in {"this", "that", "it", "something", "anything"}

    def _unique(self, candidates: list[dict]) -> list[dict]:
        unique: dict[tuple[str, str], dict] = {}
        for candidate in candidates:
            key = (candidate["memory_type"], candidate["content"].lower())
            if key not in unique or candidate["confidence_score"] > unique[key]["confidence_score"]:
                unique[key] = candidate
        return list(unique.values())
