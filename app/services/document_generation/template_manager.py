from __future__ import annotations

from app.services.document_generation.schemas import DocumentTemplate


class TemplateManager:
    templates: list[DocumentTemplate] = [
        DocumentTemplate(id="workflow-document", name="Workflow Execution Plan", kind="docx", agent_id="bolt", sections=["Workflow Overview", "Goal", "Scope and Assumptions", "Execution Phases", "Task Plan", "Dependencies", "Timeline and Deadlines", "Risks and Mitigations", "Success Checks", "Immediate Next Actions"]),
        DocumentTemplate(id="project-report", name="Project Report", kind="docx", agent_id="atlas", sections=["Project Overview", "Objective", "Scope", "System Design", "Key Components", "Implementation Plan", "Testing and Evaluation", "Risks and Constraints", "Conclusion", "Next Steps"]),
        DocumentTemplate(id="startup-business-plan", name="Startup Business Plan", kind="docx", agent_id="zeus", sections=["Executive Summary", "Problem", "Solution", "Market", "Business Model", "Go-To-Market", "Financial Plan"]),
        DocumentTemplate(id="business-proposal", name="Business Proposal", kind="docx", agent_id="zeus", sections=["Objective", "Scope", "Approach", "Timeline", "Pricing", "Next Steps"]),
        DocumentTemplate(id="research-report", name="Research Report", kind="docx", agent_id="nova", sections=["Executive Summary", "Methodology", "Key Findings", "Market Signals", "Recommendations", "Sources"]),
        DocumentTemplate(id="meeting-notes", name="Meeting Notes", kind="docx", agent_id="friday", sections=["Attendees", "Agenda", "Discussion", "Decisions", "Action Items"]),
        DocumentTemplate(id="student-assignment", name="Student Assignment", kind="docx", agent_id="alex", sections=["Introduction", "Concepts", "Analysis", "Conclusion", "References"]),
        DocumentTemplate(id="technical-documentation", name="Technical Documentation", kind="docx", agent_id="atlas", sections=["Overview", "Architecture", "APIs", "Data Model", "Deployment", "Risks"]),
        DocumentTemplate(id="startup-pitch-deck", name="Startup Pitch Deck", kind="pptx", agent_id="zeus", sections=["Title", "Problem", "Solution", "Market", "Product", "Business Model", "Traction", "Ask"]),
        DocumentTemplate(id="research-presentation", name="Research Presentation", kind="pptx", agent_id="nova", sections=["Title", "Research Question", "Findings", "Trends", "Implications", "Recommendations"]),
        DocumentTemplate(id="technical-presentation", name="Technical Presentation", kind="pptx", agent_id="atlas", sections=["Title", "System Context", "Architecture", "Components", "Roadmap", "Risks"]),
        DocumentTemplate(id="content-calendar", name="Content Calendar", kind="xlsx", agent_id="friday", sections=["Date", "Channel", "Topic", "Format", "Owner", "Status"]),
        DocumentTemplate(id="revenue-model", name="Revenue Model", kind="xlsx", agent_id="zeus", sections=["Month", "Users", "Conversion", "Revenue", "Costs", "Profit"]),
        DocumentTemplate(id="project-tracker", name="Project Tracker", kind="xlsx", agent_id="bolt", sections=["Task", "Owner", "Priority", "Status", "Due Date", "Notes"]),
        DocumentTemplate(id="executive-summary", name="Executive Summary", kind="pdf", agent_id="zeus", sections=["Summary", "Key Points", "Risks", "Recommendations"]),
        DocumentTemplate(id="study-notes", name="Study Notes", kind="pdf", agent_id="alex", sections=["Overview", "Important Concepts", "Examples", "Revision Summary"]),
        DocumentTemplate(id="strategy-report", name="Strategy Report", kind="pdf", agent_id="zeus", sections=["Context", "Strategic Options", "Recommendation", "Execution Plan"]),
    ]

    def list(self, kind: str | None = None, agent_id: str | None = None) -> list[DocumentTemplate]:
        return [item for item in self.templates if (not kind or item.kind == kind) and (not agent_id or item.agent_id == agent_id)]

    def get(self, template_id: str) -> DocumentTemplate:
        for template in self.templates:
            if template.id == template_id:
                return template
        raise ValueError(f"Unknown template: {template_id}")

    def route(self, prompt: str, kind: str) -> DocumentTemplate:
        normalized = prompt.lower()
        if kind == "docx" and "workflow" in normalized:
            return self.get("workflow-document")
        if kind == "docx" and "report" in normalized:
            return self.get("project-report")
        if kind == "pdf" and any(term in normalized for term in ["startup", "marketing", "strategy", "planning", "launch", "business plan"]):
            return self.get("strategy-report")
        if any(term in normalized for term in ["architecture", "technical", "api", "system design"]):
            agent = "atlas"
        elif any(term in normalized for term in ["research", "competitor", "industry", "market overview"]):
            agent = "nova"
        elif any(term in normalized for term in ["content", "campaign", "calendar", "social"]):
            agent = "friday"
        elif any(term in normalized for term in ["study", "learning", "goal", "travel"]):
            agent = "alex"
        elif any(term in normalized for term in ["task", "execution", "workflow", "tracker"]):
            agent = "bolt"
        else:
            agent = "zeus"
        matches = self.list(kind=kind, agent_id=agent)
        return matches[0] if matches else self.list(kind=kind)[0]
