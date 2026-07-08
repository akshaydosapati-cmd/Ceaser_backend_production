from __future__ import annotations

import re


class DesktopIntentClassifier:
    desktop_apps = {
        "chrome": "chrome",
        "edge": "edge",
        "vs code": "vscode",
        "vscode": "vscode",
        "visual studio code": "vscode",
        "notepad": "notepad",
        "calculator": "calculator",
        "file explorer": "explorer",
        "explorer": "explorer",
        "powerpoint": "powerpoint",
        "word": "word",
        "excel": "excel",
    }

    def classify(self, command: str) -> dict:
        text = command.strip()
        normalized = text.lower()
        desktop = self._desktop_action(text, normalized)
        if desktop:
            return desktop
        agent = self._agent_action(text, normalized)
        if agent:
            return agent
        return {
            "intent": "chat_action",
            "action": "chat",
            "parameters": {"message": text},
            "requires_confirmation": False,
            "active_agent": "CEASER",
            "agent_action": "chat",
            "overlay_mode": "expanded",
            "overlay_state": "thinking",
            "progress_steps": self._steps(["Understanding request", "Checking memory", "Preparing response"]),
            "result_preview": {"title": "CEASER Response", "summary": "The request will be handled by the normal CEASER chat pipeline."},
        }

    def _desktop_action(self, command: str, normalized: str) -> dict | None:
        music = self._music_action(command, normalized)
        if music:
            return music
        if re.search(r"\b(summarize|summarise|explain|read)\b", normalized) and re.search(r"\b(pdf|document|file)\b", normalized) and re.search(r"\b(viewing|reading|open|current|screen)\b", normalized):
            return self._desktop("summarize_active_pdf", {}, False, ["Identifying active PDF", "Uploading to CEASER", "Summarizing document"])
        if "screenshot" in normalized:
            return self._desktop("take_screenshot", {"save": True}, True, ["Checking screenshot permission", "Capturing screen", "Saving screenshot"])
        if "clipboard" in normalized and any(term in normalized for term in ["read", "show", "what"]):
            return self._desktop("read_clipboard", {}, False, ["Checking clipboard permission", "Reading clipboard"])
        if "downloads" in normalized:
            return self._desktop("open_folder", {"folder": "downloads"}, False, ["Checking app launch permission", "Opening Downloads"])
        if "documents" in normalized:
            return self._desktop("open_folder", {"folder": "documents"}, False, ["Checking app launch permission", "Opening Documents"])
        folder_match = re.search(r"create (?:a )?folder (?:called|named)?\s*(.+?)(?: in (downloads|documents))?$", normalized)
        if folder_match:
            return self._desktop("create_folder", {"name": folder_match.group(1).strip(), "base": folder_match.group(2) or "documents"}, True, ["Checking file write permission", "Waiting for confirmation", "Creating folder"])
        for phrase, app_id in self.desktop_apps.items():
            if re.search(rf"\b(open|launch|start)\s+{re.escape(phrase)}\b", normalized):
                return self._desktop("open_app", {"app": app_id, "label": phrase.title()}, False, ["Checking app launch permission", f"Opening {phrase.title()}"])
        return None

    def _music_action(self, command: str, normalized: str) -> dict | None:
        play = re.match(r"^(?:please\s+)?play\s+(.+?)(?:\s+(?:song|music|video))?(?:\s+(?:on|in)\s+youtube)?$", normalized)
        if play and "playwright" not in play.group(1):
            return self._desktop("play_youtube", {"query": play.group(1).strip()}, False, ["Opening YouTube", "Starting first result"])
        if re.search(r"\b(pause|resume|continue|toggle)\b.*\b(music|song|video|playback)\b", normalized) or re.match(r"^(pause|resume|continue)$", normalized):
            return self._desktop("media_key", {"key": "playpause"}, False, ["Sending media key"])
        if re.search(r"\b(next|skip)\b.*\b(song|track|music|video)\b", normalized):
            return self._desktop("media_key", {"key": "next"}, False, ["Sending media key"])
        if re.search(r"\b(previous|prev|back)\b.*\b(song|track|music|video)\b", normalized):
            return self._desktop("media_key", {"key": "previous"}, False, ["Sending media key"])
        if re.search(r"\b(forward|seek forward)\b", normalized):
            return self._desktop("media_key", {"key": "forward"}, False, ["Sending seek key"])
        if re.search(r"\b(rewind|seek back|back 10 seconds|go back)\b", normalized):
            return self._desktop("media_key", {"key": "rewind"}, False, ["Sending seek key"])
        if re.search(r"\b(show|what'?s|what is)\b.*\b(now playing|playing now|current song)\b", normalized):
            return self._desktop("now_playing", {}, False, ["Checking player"])
        return None

    def _agent_action(self, command: str, normalized: str) -> dict | None:
        rules = [
            ("Nova", "research", ["research", "sources", "competitor", "market", "trend"], ["Understanding query", "Searching sources", "Reading articles", "Analyzing data", "Building report"]),
            ("Zeus", "strategy", ["strategy", "business", "growth", "revenue", "pitch"], ["Understanding business goal", "Checking startup memory", "Building strategy", "Preparing recommendations"]),
            ("Atlas", "architecture", ["architecture", "technical", "api", "build", "software"], ["Understanding system goal", "Reviewing technical context", "Designing modules", "Preparing architecture"]),
            ("Friday", "content", ["content", "campaign", "linkedin", "social", "calendar"], ["Understanding audience", "Building content pillars", "Drafting posts", "Preparing calendar"]),
            ("Alex", "study_plan", ["study", "exam", "learn", "revision", "personal"], ["Understanding learning goal", "Checking study material", "Building roadmap", "Preparing notes"]),
            ("Bolt", "execution_plan", ["launch", "execute", "task", "workflow", "plan"], ["Understanding objective", "Breaking down milestones", "Assigning priorities", "Preparing execution plan"]),
        ]
        for agent, action, terms, steps in rules:
            if any(term in normalized for term in terms):
                return {
                    "intent": "agent_action",
                    "action": "run_agent",
                    "parameters": {"message": command},
                    "requires_confirmation": False,
                    "active_agent": agent,
                    "agent_action": action,
                    "overlay_mode": "expanded",
                    "overlay_state": "working",
                    "progress_steps": self._steps(steps),
                    "result_preview": {"title": f"{agent} Working", "summary": command},
                }
        return None

    def _desktop(self, action: str, parameters: dict, confirm: bool, steps: list[str]) -> dict:
        permission = self._permission_for(action)
        return {
            "intent": "desktop_action",
            "intent_type": "desktop_action",
            "action": action,
            "parameters": parameters,
            "requires_confirmation": confirm,
            "requires_permission": permission is not None,
            "required_permission": permission,
            "risk_level": "medium" if confirm else "low",
            "active_agent": "CEASER",
            "agent_action": None,
            "overlay_mode": "compact",
            "overlay_state": "waiting_confirmation" if confirm else "working",
            "progress_steps": self._steps(steps),
            "result_preview": {"title": action.replace("_", " ").title(), "summary": parameters.get("label") or parameters.get("folder") or parameters.get("name") or ""},
        }

    def _steps(self, labels: list[str]) -> list[dict]:
        return [{"label": label, "status": "pending"} for label in labels]

    def _permission_for(self, action: str) -> str | None:
        return None
