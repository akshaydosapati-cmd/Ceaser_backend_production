from __future__ import annotations

from app.services.workflows.schemas import WorkflowTemplate


WORKFLOW_TEMPLATES = [
    WorkflowTemplate(id="research", name="Research Workflow", description="Nova researches and produces source-backed intelligence.", agents=["Nova"]),
    WorkflowTemplate(id="research_strategy", name="Research + Strategy Workflow", description="Nova researches, then Zeus turns findings into strategy.", agents=["Nova", "Zeus"]),
    WorkflowTemplate(id="learning", name="Learning Workflow", description="Nova gathers learning context, then Alex creates study plans, revision schedules, and preparation guidance.", agents=["Nova", "Alex"]),
    WorkflowTemplate(id="career", name="Career Preparation Workflow", description="Alex and Bolt prepare applications, interview plans, and action steps.", agents=["Alex", "Bolt"]),
    WorkflowTemplate(id="document", name="Document Creation Workflow", description="Friday creates document-ready content without live research unless requested.", agents=["Friday"]),
    WorkflowTemplate(id="content", name="Content Creation Workflow", description="Friday creates content plans, campaigns, posts, and messaging.", agents=["Friday"]),
    WorkflowTemplate(id="strategy", name="Strategy Workflow", description="Zeus creates business plans, strategy, GTM, and growth direction.", agents=["Zeus"]),
    WorkflowTemplate(id="research_content", name="Research + Content Workflow", description="Nova researches, then Friday creates content direction.", agents=["Nova", "Friday"]),
    WorkflowTemplate(id="build_strategy", name="Research + Strategy + Technical Planning Workflow", description="Nova researches, Zeus frames strategy, Atlas adds lightweight technical planning.", agents=["Nova", "Zeus", "Atlas"]),
    WorkflowTemplate(id="startup", name="Startup Workflow", description="Nova, Zeus, Bolt, and Friday collaborate on launch planning.", agents=["Nova", "Zeus", "Bolt", "Friday"]),
    WorkflowTemplate(id="execution", name="Execution Workflow", description="Nova validates context, Zeus frames strategy, Bolt builds the roadmap.", agents=["Nova", "Zeus", "Bolt"]),
    WorkflowTemplate(id="technical", name="Technical Workflow", description="Atlas handles lightweight technical architecture and planning.", agents=["Atlas"]),
]


class WorkflowTemplateRegistry:
    def list(self) -> list[WorkflowTemplate]:
        return WORKFLOW_TEMPLATES

    def get(self, workflow_type: str) -> WorkflowTemplate:
        for template in WORKFLOW_TEMPLATES:
            if template.id == workflow_type:
                return template
        return WORKFLOW_TEMPLATES[0]
