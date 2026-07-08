from __future__ import annotations

import re
from urllib.parse import urlparse

from app.core.database.session import SessionLocal
from app.models.conversation import Message


AGENT_PROFILES = {
    "Bolt": {
        "domain": "Automation Intelligence",
        "frameworks_used": ["Workflow Automation", "Process Design", "Task Routing"],
    },
    "Alex": {
        "domain": "Personal Intelligence",
        "frameworks_used": ["Personal Planning", "Lifestyle Systems", "Decision Support"],
    },
    "Friday": {
        "domain": "Content Intelligence",
        "frameworks_used": ["Content Strategy", "Calendar Planning", "Audience Fit"],
    },
    "Zeus": {
        "domain": "Business Intelligence",
        "frameworks_used": ["Business Model Canvas", "SWOT Analysis", "Go-To-Market Strategy"],
    },
    "Nova": {
        "domain": "Research Intelligence",
        "frameworks_used": ["Market Research", "Competitor Analysis", "Industry Analysis"],
    },
    "Atlas": {
        "domain": "Software Intelligence",
        "frameworks_used": ["System Architecture", "Product Engineering", "Technical Planning"],
    },
}


def selected_agents_from_content(content: str) -> list[str]:
    coordinated = re.search(r"CEASER coordinated \d+ specialist agents?: ([^.]+)\.", content, flags=re.I)
    if coordinated:
        names = []
        for part in coordinated.group(1).split(","):
            name = re.sub(r"\([^)]*\)", "", part).strip()
            if name in AGENT_PROFILES and name not in names:
                names.append(name)
        if names:
            return names

    text = content.lower()
    names: list[str] = []
    keyword_map = [
        ("Atlas", ("build", "saas", "software", "platform", "engineering", "architecture")),
        ("Zeus", ("business", "strategy", "startup", "growth", "revenue", "go-to-market", "market")),
        ("Nova", ("research", "sources", "competitor", "industry", "healthcare startups", "diagnostics")),
        ("Friday", ("content", "calendar", "post", "campaign", "copy")),
        ("Bolt", ("automate", "workflow", "task", "trigger")),
        ("Alex", ("personal", "routine", "fitness", "habit")),
    ]
    for name, keywords in keyword_map:
        if any(keyword in text for keyword in keywords):
            names.append(name)
    return names or ["Zeus"]


def workspace_from_content(content: str) -> str | None:
    match = re.search(r"\b(startup|personal|creator)\s+workspace\b", content, flags=re.I)
    return match.group(1).lower() if match else None


def contribution_summary(content: str, selected_agents: list[str]) -> str:
    coordinated = re.search(r"(CEASER coordinated \d+ specialist agents?: [^.]+\.)", content, flags=re.I)
    if coordinated:
        return coordinated.group(1)
    domains = ", ".join(f"{name} ({AGENT_PROFILES[name]['domain']})" for name in selected_agents)
    return f"CEASER coordinated {len(selected_agents)} specialist agents: {domains}."


def build_contributions(content: str, selected_agents: list[str]) -> list[dict]:
    first_paragraph = next((part.strip() for part in re.split(r"\n\s*\n", content) if part.strip()), content[:220].strip())
    return [
        {
            "agent": name,
            "domain": AGENT_PROFILES[name]["domain"],
            "analysis": first_paragraph[:500],
            "recommendations": [],
            "frameworks_used": AGENT_PROFILES[name]["frameworks_used"],
            "confidence": 0.78,
        }
        for name in selected_agents
    ]


def url_from_domain(domain: str) -> str:
    parsed = urlparse(domain if domain.startswith(("http://", "https://")) else f"https://{domain}")
    return parsed.geturl()


def research_from_content(content: str) -> dict | None:
    if "source" not in content.lower() and not re.search(r"\[\d+\]", content):
        return None

    sources: list[dict] = []
    source_block = re.split(r"\bSources:\b", content, flags=re.I)
    if len(source_block) > 1:
        for line in source_block[-1].splitlines():
            match = re.match(r"\s*\d+\.\s+(.+?)(?:\s+\(([^)]+)\))?\s*$", line.strip())
            if not match:
                continue
            title = match.group(1).strip().rstrip(".")
            domain = (match.group(2) or "").strip()
            if not title:
                continue
            url = url_from_domain(domain) if "." in domain else "#"
            sources.append(
                {
                    "title": title,
                    "url": url,
                    "source": domain or "Saved response",
                    "snippet": title,
                    "score": 0.7,
                }
            )

    if not sources:
        domains = sorted(set(re.findall(r"\b(?:[a-z0-9-]+\.)+[a-z]{2,}\b", content, flags=re.I)))
        sources = [
            {
                "title": domain,
                "url": url_from_domain(domain),
                "source": domain,
                "snippet": "Referenced in the saved response.",
                "score": 0.65,
            }
            for domain in domains[:6]
        ]

    if not sources:
        return None

    return {
        "query": "Recovered from saved chat",
        "summary": "Research sources recovered from the saved assistant response.",
        "key_findings": [],
        "sources": sources[:6],
        "citations": [{"title": source["title"], "url": source["url"]} for source in sources[:6]],
    }


def metadata_from_content(content: str) -> dict:
    selected_agents = selected_agents_from_content(content)
    metadata = {
        "workspace": workspace_from_content(content),
        "selected_agents": selected_agents,
        "contributions": build_contributions(content, selected_agents),
        "contribution_summary": contribution_summary(content, selected_agents),
        "memories_used": [],
        "research": research_from_content(content),
        "context_summary": {"recovered_from_saved_message": True},
    }
    return {key: value for key, value in metadata.items() if value is not None}


def main() -> None:
    db = SessionLocal()
    try:
        messages = db.query(Message).filter(Message.role == "assistant").all()
        updated = 0
        for message in messages:
            if message.extra_metadata:
                continue
            message.extra_metadata = metadata_from_content(message.content)
            updated += 1
        db.commit()
        print(f"Backfilled metadata for {updated} assistant messages.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
