from __future__ import annotations

AGENT_ROUTING_RULES: dict[str, dict[str, object]] = {
    "Nova": {
        "domains": ["research", "search", "web", "market", "competitor", "competitors", "analysis", "analyze", "insight", "healthcare", "digital", "interoperable"],
        "weight": 3,
    },
    "Zeus": {
        "domains": ["business", "startup", "plan", "strategy", "growth", "revenue", "saas"],
        "weight": 3,
    },
    "Friday": {
        "domains": ["content", "write", "email", "blog", "copy", "script", "post"],
        "weight": 2,
    },
    "Alex": {
        "domains": ["personal", "life", "habit", "routine", "wellness", "schedule"],
        "weight": 2,
    },
    "Bolt": {
        "domains": ["task", "todo", "reminder", "workflow", "organize", "action"],
        "weight": 2,
    },
    "Atlas": {
        "domains": ["engineering", "code", "build", "software", "app", "technical", "saas"],
        "weight": 2,
    },
}

DEFAULT_AGENT = "Bolt"
