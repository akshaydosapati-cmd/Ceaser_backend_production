import sys
from pathlib import Path

from sqlalchemy import inspect, text
from sqlalchemy.exc import SQLAlchemyError

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.config.settings import settings

REQUIRED_ENV = [
    "SUPABASE_URL",
    "SUPABASE_ANON_KEY",
    "SUPABASE_SERVICE_ROLE_KEY",
    "DATABASE_URL",
]

PLACEHOLDER_MARKERS = ("[", "]", "<", ">")
DATABASE_URL_SCHEMES = ("postgresql://", "postgresql+psycopg://", "postgresql+psycopg2://")

REQUIRED_TABLES = {
    "users",
    "profiles",
    "workspaces",
    "agents",
    "agent_modules",
    "projects",
    "files",
    "conversations",
    "messages",
    "memories",
}


def main() -> None:
    missing = []
    values = {
        "SUPABASE_URL": settings.supabase_url,
        "SUPABASE_ANON_KEY": settings.supabase_anon_key,
        "SUPABASE_SERVICE_ROLE_KEY": settings.supabase_service_role_key,
        "DATABASE_URL": settings.database_url,
    }
    for key in REQUIRED_ENV:
        value = values.get(key)
        if not value or any(marker in value for marker in PLACEHOLDER_MARKERS):
            missing.append(key)

    if missing:
        raise SystemExit(f"Missing or placeholder environment variables: {', '.join(missing)}")

    if not settings.database_url.startswith(DATABASE_URL_SCHEMES):
        raise SystemExit("DATABASE_URL must be a PostgreSQL connection string, not the Supabase project API URL.")

    from app.core.database.session import engine

    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
            tables = set(inspect(connection).get_table_names())
    except SQLAlchemyError as exc:
        raise SystemExit(f"Database validation failed: {exc.__class__.__name__}") from exc

    missing_tables = REQUIRED_TABLES - tables
    if missing_tables:
        raise SystemExit(f"Missing database tables: {', '.join(sorted(missing_tables))}")

    print("Infrastructure validation passed")


if __name__ == "__main__":
    main()
