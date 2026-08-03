"""add project members

Revision ID: 20260803_0023
Revises: 20260802_0022
Create Date: 2026-08-03
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op


revision: str = "20260803_0023"
down_revision: str | None = "20260802_0022"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "project_members",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("project_id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=True),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=True),
        sa.Column("role", sa.String(length=40), nullable=False, server_default="viewer"),
        sa.Column("status", sa.String(length=40), nullable=False, server_default="invited"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("project_id", "email", name="uq_project_members_project_email"),
    )
    op.create_index(op.f("ix_project_members_project_id"), "project_members", ["project_id"], unique=False)
    op.create_index(op.f("ix_project_members_user_id"), "project_members", ["user_id"], unique=False)
    op.create_index(op.f("ix_project_members_email"), "project_members", ["email"], unique=False)
    op.execute("alter table public.project_members enable row level security")
    op.execute(
        """
        create policy project_members_project_owner_access
        on public.project_members
        for all
        to authenticated
        using (
            exists (
                select 1 from public.projects
                where projects.id = project_members.project_id
                  and projects.user_id = auth.uid()::text
            )
        )
        with check (
            exists (
                select 1 from public.projects
                where projects.id = project_members.project_id
                  and projects.user_id = auth.uid()::text
            )
        )
        """
    )
    op.execute(
        """
        INSERT INTO project_members (id, created_at, project_id, user_id, email, name, role, status)
        SELECT gen_random_uuid()::text, now(), projects.id, users.id, lower(users.email), split_part(users.email, '@', 1), 'owner', 'active'
        FROM projects
        JOIN users ON users.id = projects.user_id
        ON CONFLICT DO NOTHING
        """
    )


def downgrade() -> None:
    op.execute("drop policy if exists project_members_project_owner_access on public.project_members")
    op.drop_index(op.f("ix_project_members_email"), table_name="project_members")
    op.drop_index(op.f("ix_project_members_user_id"), table_name="project_members")
    op.drop_index(op.f("ix_project_members_project_id"), table_name="project_members")
    op.drop_table("project_members")
