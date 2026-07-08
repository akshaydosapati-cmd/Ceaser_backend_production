from __future__ import annotations


class AutomationAgentRouter:
    AGENT_BY_TYPE = {
        "research": "nova",
        "news": "nova",
        "business": "zeus",
        "content": "friday",
        "learning": "alex",
        "execution": "bolt",
        "engineering": "atlas",
    }

    def route(self, automation_type: str) -> str:
        return self.AGENT_BY_TYPE.get(automation_type.lower(), "bolt")
