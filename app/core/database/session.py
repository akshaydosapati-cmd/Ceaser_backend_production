from collections.abc import Generator
from contextvars import ContextVar
from time import perf_counter

from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.config.settings import settings

_is_sqlite = settings.database_url.startswith("sqlite")
_database_query_count: ContextVar[int] = ContextVar("database_query_count", default=0)
_database_query_ms: ContextVar[float] = ContextVar("database_query_ms", default=0.0)
_engine_options = {"pool_pre_ping": True}
if _is_sqlite:
    _engine_options["connect_args"] = {"check_same_thread": False}
    if settings.database_url.rstrip("/") == "sqlite:":
        _engine_options["poolclass"] = StaticPool

engine = create_engine(settings.database_url, **_engine_options)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


def begin_database_timing():
    return _database_query_count.set(0), _database_query_ms.set(0.0)


def database_timing() -> tuple[int, float]:
    return _database_query_count.get(), round(_database_query_ms.get(), 2)


def end_database_timing(tokens) -> None:
    _database_query_count.reset(tokens[0])
    _database_query_ms.reset(tokens[1])


@event.listens_for(engine, "before_cursor_execute")
def _before_cursor_execute(conn, cursor, statement, parameters, context, executemany):
    context._ceaser_query_started_at = perf_counter()


@event.listens_for(engine, "after_cursor_execute")
def _after_cursor_execute(conn, cursor, statement, parameters, context, executemany):
    started_at = getattr(context, "_ceaser_query_started_at", None)
    if started_at is not None:
        _database_query_count.set(_database_query_count.get() + 1)
        _database_query_ms.set(_database_query_ms.get() + (perf_counter() - started_at) * 1000)


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
