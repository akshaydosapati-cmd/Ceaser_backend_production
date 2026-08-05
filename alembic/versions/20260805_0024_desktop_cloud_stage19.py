"""Add desktop auth, devices, and cloud resources.

Revision ID: 20260805_0024
Revises: 20260803_0023
Create Date: 2026-08-05
"""

from alembic import op
import sqlalchemy as sa


revision = "20260805_0024"
down_revision = "20260803_0023"
branch_labels = None
depends_on = None


def _enable_owner_rls(table: str, user_column: str = "user_id") -> None:
    op.execute(f"alter table {table} enable row level security")
    op.execute(
        f"""
        do $$
        begin
            if not exists (
                select 1 from pg_policies
                where schemaname = current_schema()
                  and tablename = '{table}'
                  and policyname = '{table}_owner_policy'
            ) then
                create policy {table}_owner_policy on {table}
                    using ({user_column}::text = auth.uid()::text)
                    with check ({user_column}::text = auth.uid()::text);
            end if;
        end $$;
        """
    )


def upgrade() -> None:
    op.create_table(
        "desktop_auth_codes",
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("code_hash", sa.String(length=128), nullable=False),
        sa.Column("state", sa.String(length=160), nullable=False),
        sa.Column("code_challenge", sa.String(length=160), nullable=False),
        sa.Column("code_challenge_method", sa.String(length=16), nullable=False),
        sa.Column("device_id", sa.String(length=120), nullable=False),
        sa.Column("device_name", sa.String(length=255), nullable=True),
        sa.Column("platform", sa.String(length=80), nullable=True),
        sa.Column("app_version", sa.String(length=80), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_desktop_auth_codes_code_hash", "desktop_auth_codes", ["code_hash"], unique=True)
    op.create_index("ix_desktop_auth_codes_device_id", "desktop_auth_codes", ["device_id"])
    op.create_index("ix_desktop_auth_codes_state", "desktop_auth_codes", ["state"])
    op.create_index("ix_desktop_auth_codes_user_id", "desktop_auth_codes", ["user_id"])

    op.create_table(
        "desktop_refresh_sessions",
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("device_id", sa.String(length=120), nullable=False),
        sa.Column("token_hash", sa.String(length=128), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_desktop_refresh_sessions_device_id", "desktop_refresh_sessions", ["device_id"])
    op.create_index("ix_desktop_refresh_sessions_token_hash", "desktop_refresh_sessions", ["token_hash"], unique=True)
    op.create_index("ix_desktop_refresh_sessions_user_id", "desktop_refresh_sessions", ["user_id"])

    op.create_table(
        "desktop_devices",
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("device_id", sa.String(length=120), nullable=False),
        sa.Column("device_name", sa.String(length=255), nullable=False),
        sa.Column("platform", sa.String(length=80), nullable=True),
        sa.Column("app_version", sa.String(length=80), nullable=True),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_desktop_devices_device_id", "desktop_devices", ["device_id"])
    op.create_index("ix_desktop_devices_user_id", "desktop_devices", ["user_id"])

    op.create_table(
        "desktop_cloud_resources",
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("project_id", sa.String(length=36), nullable=True),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("resource_type", sa.String(length=80), nullable=False),
        sa.Column("mime_type", sa.String(length=160), nullable=True),
        sa.Column("storage_path", sa.String(length=1000), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("metadata_json", sa.JSON(), nullable=False),
        sa.Column("content_encrypted", sa.Text(), nullable=True),
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_desktop_cloud_resources_name", "desktop_cloud_resources", ["name"])
    op.create_index("ix_desktop_cloud_resources_project_id", "desktop_cloud_resources", ["project_id"])
    op.create_index("ix_desktop_cloud_resources_resource_type", "desktop_cloud_resources", ["resource_type"])
    op.create_index("ix_desktop_cloud_resources_status", "desktop_cloud_resources", ["status"])
    op.create_index("ix_desktop_cloud_resources_user_id", "desktop_cloud_resources", ["user_id"])

    for table in ("desktop_auth_codes", "desktop_refresh_sessions", "desktop_devices", "desktop_cloud_resources"):
        _enable_owner_rls(table)


def downgrade() -> None:
    op.drop_table("desktop_cloud_resources")
    op.drop_table("desktop_devices")
    op.drop_table("desktop_refresh_sessions")
    op.drop_table("desktop_auth_codes")
