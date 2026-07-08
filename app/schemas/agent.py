from pydantic import BaseModel

from app.schemas.common import ORMModel


class AgentModuleRead(ORMModel):
    id: str
    agent_id: str
    module_name: str
    enabled: bool


class AgentRead(ORMModel):
    id: str
    user_id: str
    name: str
    enabled: bool
    modules: list[AgentModuleRead] = []


class AgentUpdate(BaseModel):
    enabled: bool | None = None


class AgentModulesUpdate(BaseModel):
    module_names: list[str] | None = None
    moduleIds: list[str] | None = None
