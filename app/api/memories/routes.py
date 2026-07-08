from typing import Annotated

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.core.database.session import get_db
from app.core.security.access_control import require_memory_access
from app.core.security.dependencies import get_current_user
from app.models.user import User
from app.schemas.memory import MemoryCreate, MemoryRead, MemorySearch
from app.services.audit_service import AuditService
from app.services.memory_service import MemoryService

router = APIRouter(prefix="/memories", tags=["memories"])
memory_alias_router = APIRouter(prefix="/memory", tags=["memory"])


@router.get("", response_model=list[MemoryRead])
def list_memories(user: Annotated[User, Depends(get_current_user)], db: Annotated[Session, Depends(get_db)]):
    memories = MemoryService(db).list(user_id=user.id)
    AuditService(db).record(user_id=user.id, action="memory_read", resource_type="memory", metadata={"count": len(memories)})
    return memories


@router.post("", response_model=MemoryRead, status_code=status.HTTP_201_CREATED)
def create_memory(payload: MemoryCreate, user: Annotated[User, Depends(get_current_user)], db: Annotated[Session, Depends(get_db)]):
    memory = MemoryService(db).create(user_id=user.id, memory_type=payload.memory_type, content=payload.content, metadata=payload.metadata)
    AuditService(db).record(user_id=user.id, action="memory_created", resource_type="memory", resource_id=memory.id)
    return memory


@router.post("/search", response_model=list[MemoryRead])
def search_memories(payload: MemorySearch, user: Annotated[User, Depends(get_current_user)], db: Annotated[Session, Depends(get_db)]):
    memories = MemoryService(db).search(query=payload.query, user_id=user.id)
    AuditService(db).record(user_id=user.id, action="memory_read", resource_type="memory", metadata={"count": len(memories), "search": True})
    return memories


@router.get("/{memory_id}", response_model=MemoryRead)
def get_memory(memory_id: str, user: Annotated[User, Depends(get_current_user)], db: Annotated[Session, Depends(get_db)]):
    memory = require_memory_access(db, user, memory_id)
    AuditService(db).record(user_id=user.id, action="memory_read", resource_type="memory", resource_id=memory.id)
    return memory


@router.delete("/{memory_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_memory(memory_id: str, user: Annotated[User, Depends(get_current_user)], db: Annotated[Session, Depends(get_db)]):
    memory = require_memory_access(db, user, memory_id)
    MemoryService(db).delete(memory)
    AuditService(db).record(user_id=user.id, action="memory_deleted", resource_type="memory", resource_id=memory_id)
    return None


@memory_alias_router.get("", response_model=list[MemoryRead])
def list_memory_alias(user: Annotated[User, Depends(get_current_user)], db: Annotated[Session, Depends(get_db)]):
    return list_memories(user, db)


@memory_alias_router.get("/search", response_model=list[MemoryRead])
def search_memory_alias(query: str = "", user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return MemoryService(db).search(query=query, user_id=user.id)


@memory_alias_router.get("/graph")
def memory_graph_alias(user: Annotated[User, Depends(get_current_user)]):
    return {"nodes": [], "links": []}
