from __future__ import annotations


SECTION_BY_AGENT = {
    "Nova": "Research",
    "Zeus": "Strategy",
    "Bolt": "Execution",
    "Friday": "Content",
    "Alex": "Learning",
    "Atlas": "Technical Plan",
}


class WorkflowMerger:
    def merge(self, *, workflow_name: str, message: str, contributions: list[dict]) -> dict:
        summary = f"{workflow_name} completed with {len(contributions)} CEASER agents."
        lines = [f"## {workflow_name}", "", "### Executive Summary", self._plain_summary(message, contributions), ""]
        for contribution in contributions:
            section = SECTION_BY_AGENT.get(contribution["agent"], contribution["domain"])
            lines.extend([f"### {section}", contribution.get("analysis", "").strip(), ""])
            recommendations = contribution.get("recommendations", [])[:4]
            if recommendations:
                lines.append("Recommendations:")
                lines.extend(f"- {item}" for item in recommendations)
                lines.append("")
        next_actions = self._next_actions(contributions)
        if next_actions:
            lines.extend(["### Next Actions", *[f"- {item}" for item in next_actions], ""])
        return {"summary": summary, "response": "\n".join(lines).strip(), "next_actions": next_actions}

    def _plain_summary(self, message: str, contributions: list[dict]) -> str:
        agents = ", ".join(item["agent"] for item in contributions)
        return f"CEASER treated this as a workforce task for: {message}. The agents involved were {agents}."

    def _next_actions(self, contributions: list[dict]) -> list[str]:
        actions = []
        for contribution in contributions:
            actions.extend(contribution.get("recommendations", [])[:1])
        return actions[:6]
