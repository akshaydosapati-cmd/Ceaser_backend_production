from app.agents.v2.definitions import AGENT_DEFINITIONS
from app.agents.v2.models import AgentDefinition


class AgentRegistry:
    def __init__(self, definitions=AGENT_DEFINITIONS):
        self._definitions: dict[str, AgentDefinition] = {}
        for definition in definitions:
            self.register(definition)

    def register(self, definition: AgentDefinition) -> None:
        key = definition.id.lower()
        if key in self._definitions:
            raise ValueError(f"duplicate agent definition: {key}")
        self._definitions[key] = definition

    def get(self, agent_id: str) -> AgentDefinition | None:
        return self._definitions.get(str(agent_id).lower())

    def enabled(self) -> list[AgentDefinition]:
        return [item for item in self._definitions.values() if item.enabled]

    def metadata(self) -> list[dict]:
        return [item.model_dump(exclude={"instructions"}) for item in self.enabled()]

    def capability_allowed(self, agent_id: str, capability: str) -> bool:
        definition = self.get(agent_id)
        return bool(definition and definition.permits(capability))
