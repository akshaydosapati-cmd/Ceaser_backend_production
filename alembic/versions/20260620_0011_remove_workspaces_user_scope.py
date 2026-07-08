"""Remove workspace ownership and use user-scoped CEASER data.

Revision ID: 20260620_0011
Revises: 20260617_0010
Create Date: 2026-06-20
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision: str = "20260620_0011"
down_revision: str | None = "20260617_0010"
branch_labels = None
depends_on = None


OWNED_TABLES = [
    "agents",
    "projects",
    "conversations",
    "memories",
    "files",
    "generated_documents",
    "agent_activity",
    "voice_sessions",
]

WORKSPACE_ONLY_TABLES = ["audit_logs", "drafts", "draft_history"]


def _has_column(table: str, column: str) -> bool:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return column in {item["name"] for item in inspector.get_columns(table)}


def _has_table(table: str) -> bool:
    return sa.inspect(op.get_bind()).has_table(table)


def _drop_constraint_if_exists(table: str, constraint: str) -> None:
    bind = op.get_bind()
    exists = bind.execute(
        sa.text(
            """
            select 1
            from information_schema.table_constraints
            where table_name = :table_name
              and constraint_name = :constraint_name
            """
        ),
        {"table_name": table, "constraint_name": constraint},
    ).first()
    if exists:
        op.drop_constraint(constraint, table, type_="foreignkey")


def _drop_index_if_exists(index_name: str, table: str) -> None:
    bind = op.get_bind()
    exists = bind.execute(
        sa.text(
            """
            select 1
            from pg_indexes
            where tablename = :table_name
              and indexname = :index_name
            """
        ),
        {"table_name": table, "index_name": index_name},
    ).first()
    if exists:
        op.drop_index(index_name, table_name=table)


def _create_index_if_missing(index_name: str, table: str, columns: list[str]) -> None:
    bind = op.get_bind()
    exists = bind.execute(
        sa.text(
            """
            select 1
            from pg_indexes
            where tablename = :table_name
              and indexname = :index_name
            """
        ),
        {"table_name": table, "index_name": index_name},
    ).first()
    if not exists:
        op.create_index(index_name, table, columns)


def upgrade() -> None:
    if not _has_table("workspaces"):
        return

    op.execute(
        sa.text(
            """
            do $$
            declare
                item record;
            begin
                for item in
                    select schemaname, tablename, policyname
                    from pg_policies
                    where schemaname = current_schema()
                      and (
                        policyname ilike '%workspace%'
                        or coalesce(qual, '') ilike '%workspace_id%'
                        or coalesce(with_check, '') ilike '%workspace_id%'
                      )
                loop
                    execute format(
                        'drop policy if exists %I on %I.%I',
                        item.policyname,
                        item.schemaname,
                        item.tablename
                    );
                end loop;
            end $$;
            """
        )
    )

    for table in OWNED_TABLES:
        if _has_table(table) and not _has_column(table, "user_id"):
            op.add_column(table, sa.Column("user_id", sa.String(length=36), nullable=True))

    for table in OWNED_TABLES:
        if _has_table(table) and _has_column(table, "workspace_id"):
            op.execute(
                sa.text(
                    f"""
                    update {table}
                    set user_id = workspaces.owner_id
                    from workspaces
                    where {table}.workspace_id = workspaces.id
                      and {table}.user_id is null
                    """
                )
            )

    for table in OWNED_TABLES:
        if _has_table(table) and _has_column(table, "user_id"):
            op.alter_column(table, "user_id", nullable=False)
            _create_index_if_missing(f"ix_{table}_user_id", table, ["user_id"])

    for table in OWNED_TABLES + WORKSPACE_ONLY_TABLES:
        if _has_table(table) and _has_column(table, "workspace_id"):
            _drop_constraint_if_exists(table, f"{table}_workspace_id_fkey")
            _drop_index_if_exists(f"ix_{table}_workspace_id", table)
            op.drop_column(table, "workspace_id")

    _drop_index_if_exists("ix_workspaces_owner_id", "workspaces")
    op.drop_table("workspaces")


def downgrade() -> None:
    raise RuntimeError("Downgrade is not supported after removing CEASER workspaces.")
