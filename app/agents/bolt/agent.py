from app.agents.base_agent import BaseAgent
from app.agents.bolt.capabilities import CAPABILITIES, CONTRIBUTION_AREAS
from app.agents.bolt.frameworks import FRAMEWORKS


class BoltAgent(BaseAgent):
    name = "Bolt"
    domain = "Execution Intelligence"
    description = "Builds action plans, task lists, execution roadmaps, and follow-up plans."
    capabilities = CAPABILITIES
    frameworks = FRAMEWORKS
    contribution_areas = CONTRIBUTION_AREAS
