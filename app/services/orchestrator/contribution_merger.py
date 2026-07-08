from __future__ import annotations


class ContributionMerger:
    def merge(self, selected_agents: list[str], contributions: list[dict]) -> dict:
        recommendations: list[str] = []
        seen: set[str] = set()
        for contribution in contributions:
            for recommendation in contribution.get("recommendations", []):
                key = recommendation.lower()
                if key not in seen:
                    seen.add(key)
                    recommendations.append(recommendation)

        summary = self._summary(contributions)
        response = self._response(summary, recommendations)
        return {
            "selected_agents": selected_agents,
            "contributions": contributions,
            "summary": summary,
            "recommendations": recommendations,
            "response": response,
        }

    def _summary(self, contributions: list[dict]) -> str:
        if not contributions:
            return "No specialist agent contributions were produced."
        domains = ", ".join(f"{item['agent']} ({item['domain']})" for item in contributions)
        return f"CEASER coordinated {len(contributions)} specialist agents: {domains}."

    def _response(self, summary: str, recommendations: list[str]) -> str:
        if not recommendations:
            return summary
        top_recommendations = "\n".join(f"- {item}" for item in recommendations[:8])
        return f"{summary}\n\nUnified direction:\n{top_recommendations}"
