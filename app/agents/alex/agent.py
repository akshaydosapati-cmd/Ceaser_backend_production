from app.agents.alex.capabilities import CAPABILITIES, CONTRIBUTION_AREAS
from app.agents.alex.frameworks import FRAMEWORKS
from app.agents.base_agent import BaseAgent


class AlexAgent(BaseAgent):
    name = "Alex"
    domain = "Personal Intelligence"
    description = "Builds personal recommendations, learning plans, productivity systems, and goal strategies."
    capabilities = CAPABILITIES
    frameworks = FRAMEWORKS
    contribution_areas = CONTRIBUTION_AREAS
