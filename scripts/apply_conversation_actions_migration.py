from sqlalchemy import text

from app.core.database.session import engine


SQL = [
    "ALTER TABLE conversations ADD COLUMN IF NOT EXISTS pinned BOOLEAN",
    "ALTER TABLE conversations ADD COLUMN IF NOT EXISTS archived BOOLEAN",
    "UPDATE conversations SET pinned = false WHERE pinned IS NULL",
    "UPDATE conversations SET archived = false WHERE archived IS NULL",
    "ALTER TABLE conversations ALTER COLUMN pinned SET NOT NULL",
    "ALTER TABLE conversations ALTER COLUMN archived SET NOT NULL",
    "UPDATE alembic_version SET version_num = '20260616_0004'",
]


def main() -> None:
    with engine.begin() as connection:
        for statement in SQL:
            connection.execute(text(statement))
    print("conversation action migration applied")


if __name__ == "__main__":
    main()
