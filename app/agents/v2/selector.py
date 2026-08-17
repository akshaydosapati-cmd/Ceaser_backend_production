from __future__ import annotations

import re

from app.agents.v2.models import AgentSelection, ExecutionTarget


class AgentSelector:
    DIRECT = re.compile(r"\b(open|close|launch)\s+(chrome|calculator|settings|explorer)|\b(pause|resume|stop)\s+(music|media)|\bset volume\b", re.I)
    BOLT = re.compile(
        r"\b(build|create|develop|implement|code|fix|debug|repair|refactor)\b.*\b(site|website|landing page|app|application|software|saas|project|react|api|code)\b"
        r"|\bfix my\s+.+project\b"
        r"|\b(write|generate|show|provide|give|draft|explain|review|optimi[sz]e)\b.{0,80}\b(code|script|function|class|component|query|regex|algorithm|html|css|javascript|typescript|python|java|c\+\+|c#|sql|react|node(?:\.js)?)\b"
        r"|\b(code|script|function|class|component|html|css|javascript|typescript|python|java|c\+\+|c#|sql|react|node(?:\.js)?)\b.{0,80}\b(for|that|which|to)\b",
        re.I,
    )
    ALEX = re.compile(r"\b(research|investigate|compare|find evidence|market research|competitor research)\b", re.I)
    NOVA = re.compile(r"\b(create|write|draft|generate)\b.*\b(campaign|caption|content|post|copy|email|announcement)\b", re.I)
    ZEUS = re.compile(r"\b(strategy|strategic|prioritize|prioritise|business plan|startup plan|launch plan|decision analysis)\b", re.I)
    ATLAS = re.compile(r"\b(organize|organise|classify|structure|synthesize|summarize)\b.*\b(documents?|files?|knowledge|data|resources?)\b", re.I)
    FRIDAY = re.compile(r"\b(plan|organize|schedule)\b.*\b(my work|my day|tomorrow|tasks?|notes?|productivity)\b", re.I)
    FOLLOW_UP = re.compile(r"^(make|change|use|why|continue|also|now|then|what about)\b", re.I)

    def select(self, message: str, *, active_agent_id: str | None = None, channel: str = "text") -> AgentSelection:
        _ = channel
        text = " ".join(str(message or "").split())
        if self.DIRECT.search(text):
            return AgentSelection(route="DIRECT_DEVICE", reason="direct_device_command", execution_target=ExecutionTarget.DEVICE)
        matches: list[str] = []
        for agent_id, pattern in (("alex", self.ALEX), ("bolt", self.BOLT), ("nova", self.NOVA), ("zeus", self.ZEUS), ("atlas", self.ATLAS), ("friday", self.FRIDAY)):
            if pattern.search(text):
                matches.append(agent_id)
        if "alex" in matches and "zeus" in matches:
            matches = ["alex", "zeus"]
        elif "alex" in matches and "nova" in matches:
            matches = ["alex", "nova"]
        if matches:
            target = ExecutionTarget.EITHER if "bolt" in matches else ExecutionTarget.NONE
            return AgentSelection(route="SPECIALIST", agent_ids=matches[:3], confidence=0.92, reason="specialist_intent", execution_target=target)
        if active_agent_id and self.FOLLOW_UP.search(text):
            return AgentSelection(route="SPECIALIST", agent_ids=[active_agent_id], confidence=0.82, reason="active_agent_follow_up")
        return AgentSelection(route="NORMAL_AI", reason="no_specialist_required")
