from app.agents.atlas.capabilities import CAPABILITIES, CONTRIBUTION_AREAS
from app.agents.atlas.frameworks import FRAMEWORKS
from app.agents.base_agent import BaseAgent


class AtlasAgent(BaseAgent):
    name = "Atlas"
    domain = "Engineering Intelligence"
    description = "Builds technical architecture, stack recommendations, system design, and engineering planning without code execution."
    capabilities = CAPABILITIES
    frameworks = FRAMEWORKS
    contribution_areas = CONTRIBUTION_AREAS
