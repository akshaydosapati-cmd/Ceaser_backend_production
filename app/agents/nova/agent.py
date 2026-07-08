from app.agents.base_agent import BaseAgent
from app.agents.nova.capabilities import CAPABILITIES, CONTRIBUTION_AREAS
from app.agents.nova.frameworks import FRAMEWORKS


class NovaAgent(BaseAgent):
    name = "Nova"
    domain = "Research Intelligence"
    description = "Builds research findings, competitor analysis, industry intelligence, and market opportunities."
    capabilities = CAPABILITIES
    frameworks = FRAMEWORKS
    contribution_areas = CONTRIBUTION_AREAS
