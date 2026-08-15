from __future__ import annotations

from app.services.workflows.schemas import WorkflowTemplate


WORKFLOW_TEMPLATES = [
    WorkflowTemplate(id="research", name="Research Workflow", description="Alex researches and produces source-backed intelligence.", agents=["Alex"]),
    WorkflowTemplate(id="research_strategy", name="Research + Strategy Workflow", description="Alex researches, then Zeus turns findings into strategy.", agents=["Alex", "Zeus"]),
    WorkflowTemplate(id="learning", name="Learning Workflow", description="Alex gathers evidence, then Friday creates a practical study plan.", agents=["Alex", "Friday"]),
    WorkflowTemplate(id="career", name="Career Preparation Workflow", description="Friday plans the process and Nova prepares application content.", agents=["Friday", "Nova"]),
    WorkflowTemplate(id="document", name="Document Creation Workflow", description="Nova creates document-ready content without live research unless requested.", agents=["Nova"]),
    WorkflowTemplate(id="content", name="Content Creation Workflow", description="Nova creates campaigns, posts, messaging, and creative direction.", agents=["Nova"]),
    WorkflowTemplate(id="strategy", name="Strategy Workflow", description="Zeus creates business plans, strategy, GTM, and growth direction.", agents=["Zeus"]),
    WorkflowTemplate(id="research_content", name="Research + Content Workflow", description="Alex researches, then Nova creates content direction.", agents=["Alex", "Nova"]),
    WorkflowTemplate(id="build_strategy", name="Research + Strategy + Technical Planning Workflow", description="Alex researches, Zeus frames strategy, and Bolt plans the software build.", agents=["Alex", "Zeus", "Bolt"]),
    WorkflowTemplate(id="startup", name="Startup Workflow", description="Alex, Zeus, and Bolt collaborate on a bounded launch plan.", agents=["Alex", "Zeus", "Bolt"]),
    WorkflowTemplate(id="execution", name="Execution Workflow", description="Zeus frames priorities, Friday organizes execution, and Bolt handles software work.", agents=["Zeus", "Friday", "Bolt"]),
    WorkflowTemplate(id="technical", name="Technical Workflow", description="Bolt handles software architecture and engineering planning.", agents=["Bolt"]),
]


class WorkflowTemplateRegistry:
    def list(self) -> list[WorkflowTemplate]:
        return WORKFLOW_TEMPLATES

    def get(self, workflow_type: str) -> WorkflowTemplate:
        for template in WORKFLOW_TEMPLATES:
            if template.id == workflow_type:
                return template
        return WORKFLOW_TEMPLATES[0]
