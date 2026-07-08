from app.agents.base_agent import BaseAgent
from app.agents.zeus.capabilities import CAPABILITIES, CONTRIBUTION_AREAS
from app.agents.zeus.frameworks import FRAMEWORKS


class ZeusAgent(BaseAgent):
    name = "Zeus"
    domain = "Business Intelligence"
    description = "Builds business strategy, revenue planning, market positioning, startup planning, and risk direction."
    capabilities = CAPABILITIES
    frameworks = FRAMEWORKS
    contribution_areas = CONTRIBUTION_AREAS
