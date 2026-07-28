"""Complete Supabase RLS coverage for all CEASER tables.

Revision ID: 20260728_0021
Revises: 20260728_0020
Create Date: 2026-07-28
"""

from __future__ import annotations

from alembic import op


revision: str = "20260728_0021"
down_revision: str | None = "20260728_0020"
branch_labels = None
depends_on = None


DIRECT_OWNER_TABLES = {
    "knowledge_sources": "user_id",
    "knowledge_retrieval_logs": "user_id",
    "context_runs": "user_id",
}

INDIRECT_OWNER_TABLES = {
    "knowledge_chunks": "exists (select 1 from public.knowledge_sources ks where ks.id = source_id and ks.user_id = auth.uid()::text)",
}

SERVICE_ROLE_TABLES = [
    "billing_events",
    "launch_waitlist",
]


def upgrade() -> None:
    for table, owner_column in DIRECT_OWNER_TABLES.items():
        condition = f"{owner_column} = auth.uid()::text"
        _enable_rls(table)
        _replace_policy(table, f"{table}_owner_access", "ALL", ["authenticated"], condition, condition)

    for table, condition in INDIRECT_OWNER_TABLES.items():
        _enable_rls(table)
        _replace_policy(table, f"{table}_owner_access", "ALL", ["authenticated"], condition, condition)

    for table in SERVICE_ROLE_TABLES:
        _enable_rls(table)
        _replace_policy(table, f"{table}_service_role_access", "ALL", ["service_role"], "true", "true")


def downgrade() -> None:
    for table in DIRECT_OWNER_TABLES:
        _drop_policy(table, f"{table}_owner_access")
    for table in INDIRECT_OWNER_TABLES:
        _drop_policy(table, f"{table}_owner_access")
    for table in SERVICE_ROLE_TABLES:
        _drop_policy(table, f"{table}_service_role_access")


def _enable_rls(table: str) -> None:
    _execute_if_table_exists(table, f"alter table public.{table} enable row level security")


def _replace_policy(table: str, name: str, operation: str, roles: list[str], using: str, check: str | None) -> None:
    check_clause = f" with check ({check})" if check else ""
    roles_clause = ", ".join(roles)
    _execute_if_table_exists(table, f"drop policy if exists {name} on public.{table}")
    _execute_if_table_exists(
        table,
        f"create policy {name} on public.{table} for {operation} to {roles_clause} using ({using}){check_clause}",
    )


def _drop_policy(table: str, name: str) -> None:
    _execute_if_table_exists(table, f"drop policy if exists {name} on public.{table}")


def _execute_if_table_exists(table: str, statement: str) -> None:
    escaped = statement.replace("'", "''")
    op.execute(
        f"""
        do $$
        begin
            if exists (
                select 1
                from information_schema.tables
                where table_schema = 'public'
                  and table_name = '{table}'
            ) then
                execute '{escaped}';
            end if;
        end $$;
        """
    )
