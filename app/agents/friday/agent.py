from app.agents.base_agent import BaseAgent
from app.agents.friday.capabilities import CAPABILITIES, CONTRIBUTION_AREAS
from app.agents.friday.frameworks import FRAMEWORKS


class FridayAgent(BaseAgent):
    name = "Friday"
    domain = "Content Intelligence"
    description = "Builds content plans, branding direction, social strategy, and marketing messaging."
    capabilities = CAPABILITIES
    frameworks = FRAMEWORKS
    contribution_areas = CONTRIBUTION_AREAS
