"""Enable Supabase row level security policies.

Revision ID: 20260706_0015
Revises: 20260621_0014
Create Date: 2026-07-06
"""

from alembic import op


revision = "20260706_0015"
down_revision = "20260621_0014"
branch_labels = None
depends_on = None


OWNER_ID_TABLES = {
    "users": "id",
    "profiles": "user_id",
    "agents": "user_id",
    "projects": "user_id",
    "conversations": "user_id",
    "memories": "user_id",
    "files": "user_id",
    "audit_logs": "user_id",
    "voice_sessions": "user_id",
    "voice_settings": "user_id",
    "generated_documents": "user_id",
    "agent_activity": "user_id",
    "drafts": "user_id",
    "draft_history": "user_id",
    "integrations": "user_id",
    "automations": "user_id",
    "automation_runs": "user_id",
    "workflow_runs": "user_id",
}

INDIRECT_TABLES = {
    "agent_modules": "exists (select 1 from public.agents a where a.id = agent_id and a.user_id = auth.uid()::text)",
    "messages": "exists (select 1 from public.conversations c where c.id = conversation_id and c.user_id = auth.uid()::text)",
    "workflow_steps": "exists (select 1 from public.workflow_runs w where w.id = workflow_id and w.user_id = auth.uid()::text)",
}

PUBLIC_READ_TABLES = ["automation_templates"]


def upgrade() -> None:
    for table, owner_column in OWNER_ID_TABLES.items():
        condition = f"{owner_column} = auth.uid()::text"
        _enable_rls(table)
        _replace_policy(table, f"{table}_owner_access", "ALL", condition, condition)

    for table, condition in INDIRECT_TABLES.items():
        _enable_rls(table)
        _replace_policy(table, f"{table}_owner_access", "ALL", condition, condition)

    for table in PUBLIC_READ_TABLES:
        _enable_rls(table)
        _replace_policy(table, f"{table}_authenticated_read", "SELECT", "true", None)


def downgrade() -> None:
    for table in [*OWNER_ID_TABLES.keys(), *INDIRECT_TABLES.keys(), *PUBLIC_READ_TABLES]:
        _drop_policy(table, f"{table}_owner_access")
        _drop_policy(table, f"{table}_authenticated_read")
        _disable_rls(table)


def _enable_rls(table: str) -> None:
    _execute_if_table_exists(table, f"alter table public.{table} enable row level security")


def _disable_rls(table: str) -> None:
    _execute_if_table_exists(table, f"alter table public.{table} disable row level security")


def _replace_policy(table: str, name: str, operation: str, using: str, check: str | None) -> None:
    check_clause = f" with check ({check})" if check else ""
    _execute_if_table_exists(table, f"drop policy if exists {name} on public.{table}")
    _execute_if_table_exists(
        table,
        f"create policy {name} on public.{table} for {operation} to authenticated using ({using}){check_clause}",
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
