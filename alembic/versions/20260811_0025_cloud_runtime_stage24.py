"""Add durable multi-user cloud runtime.

Revision ID: 20260811_0025
Revises: 20260805_0024
"""

from alembic import op
import sqlalchemy as sa


revision = "20260811_0025"
down_revision = "20260805_0024"
branch_labels = None
depends_on = None


def _owner_rls(table: str) -> None:
    op.execute(f"alter table {table} enable row level security")
    op.execute(
        f"""do $$ begin
        if not exists (select 1 from pg_policies where schemaname=current_schema() and tablename='{table}' and policyname='{table}_owner_policy') then
          create policy {table}_owner_policy on {table}
          using (user_id::text = auth.uid()::text) with check (user_id::text = auth.uid()::text);
        end if; end $$;"""
    )


def upgrade() -> None:
    op.create_table(
        "cloud_jobs",
        sa.Column("id", sa.String(36), primary_key=True), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("agent_id", sa.String(80), nullable=False), sa.Column("task_id", sa.String(120), nullable=False),
        sa.Column("request_id", sa.String(120), nullable=False), sa.Column("idempotency_key", sa.String(160)),
        sa.Column("status", sa.String(40), nullable=False), sa.Column("execution_target", sa.String(20), nullable=False),
        sa.Column("workspace_id", sa.String(36)), sa.Column("parent_job_id", sa.String(36), sa.ForeignKey("cloud_jobs.id", ondelete="SET NULL")),
        sa.Column("capability", sa.String(160), nullable=False), sa.Column("arguments_json", sa.JSON(), nullable=False),
        sa.Column("current_step", sa.String(160)), sa.Column("progress", sa.Float(), nullable=False),
        sa.Column("attempt_count", sa.Integer(), nullable=False), sa.Column("max_attempts", sa.Integer(), nullable=False),
        sa.Column("available_at", sa.DateTime(timezone=True)), sa.Column("claimed_by", sa.String(160)),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True)), sa.Column("heartbeat_at", sa.DateTime(timezone=True)),
        sa.Column("started_at", sa.DateTime(timezone=True)), sa.Column("updated_at", sa.DateTime(timezone=True)),
        sa.Column("completed_at", sa.DateTime(timezone=True)), sa.Column("cancelled_at", sa.DateTime(timezone=True)),
        sa.Column("failure_category", sa.String(80)), sa.Column("safe_error", sa.Text()), sa.Column("result_summary", sa.Text()),
        sa.Column("pending_action_json", sa.JSON()), sa.Column("metadata_json", sa.JSON(), nullable=False),
        sa.UniqueConstraint("user_id", "idempotency_key", name="uq_cloud_jobs_user_idempotency"),
    )
    for column in ("user_id", "agent_id", "task_id", "request_id", "status", "workspace_id", "capability", "claimed_by"):
        op.create_index(f"ix_cloud_jobs_{column}", "cloud_jobs", [column])
    op.create_index("ix_cloud_jobs_queue", "cloud_jobs", ["status", "available_at", "created_at"])

    op.create_table(
        "cloud_workspaces",
        sa.Column("id", sa.String(36), primary_key=True), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("job_id", sa.String(36), sa.ForeignKey("cloud_jobs.id", ondelete="CASCADE"), nullable=False, unique=True),
        sa.Column("project_id", sa.String(36), sa.ForeignKey("projects.id", ondelete="SET NULL")),
        sa.Column("status", sa.String(40), nullable=False), sa.Column("source_type", sa.String(40), nullable=False),
        sa.Column("git_repository", sa.String(500)), sa.Column("branch", sa.String(160)),
        sa.Column("storage_location", sa.String(1000), nullable=False), sa.Column("updated_at", sa.DateTime(timezone=True)),
        sa.Column("limits_json", sa.JSON(), nullable=False),
    )
    for column in ("user_id", "job_id", "status"):
        op.create_index(f"ix_cloud_workspaces_{column}", "cloud_workspaces", [column])

    op.create_table(
        "cloud_artifacts",
        sa.Column("id", sa.String(36), primary_key=True), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("job_id", sa.String(36), sa.ForeignKey("cloud_jobs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("workspace_id", sa.String(36), sa.ForeignKey("cloud_workspaces.id", ondelete="CASCADE"), nullable=False),
        sa.Column("artifact_type", sa.String(80), nullable=False), sa.Column("name", sa.String(255), nullable=False),
        sa.Column("storage_key", sa.String(1000), nullable=False, unique=True), sa.Column("content_type", sa.String(160)),
        sa.Column("size_bytes", sa.Integer(), nullable=False), sa.Column("checksum", sa.String(128)), sa.Column("metadata_json", sa.JSON(), nullable=False),
    )
    for column in ("user_id", "job_id", "workspace_id", "artifact_type"):
        op.create_index(f"ix_cloud_artifacts_{column}", "cloud_artifacts", [column])

    op.create_table(
        "cloud_job_events",
        sa.Column("id", sa.String(36), primary_key=True), sa.Column("job_id", sa.String(36), sa.ForeignKey("cloud_jobs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("event_type", sa.String(120), nullable=False), sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False), sa.Column("payload_json", sa.JSON(), nullable=False),
        sa.UniqueConstraint("job_id", "sequence", name="uq_cloud_job_events_sequence"),
    )
    for column in ("job_id", "user_id", "event_type", "timestamp"):
        op.create_index(f"ix_cloud_job_events_{column}", "cloud_job_events", [column])

    op.create_table(
        "cloud_checkpoints",
        sa.Column("id", sa.String(36), primary_key=True), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("job_id", sa.String(36), sa.ForeignKey("cloud_jobs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("workspace_id", sa.String(36), sa.ForeignKey("cloud_workspaces.id", ondelete="CASCADE"), nullable=False),
        sa.Column("step_index", sa.Integer(), nullable=False), sa.Column("state_json", sa.JSON(), nullable=False),
        sa.Column("revision_reference", sa.String(500)),
    )
    for column in ("user_id", "job_id", "workspace_id"):
        op.create_index(f"ix_cloud_checkpoints_{column}", "cloud_checkpoints", [column])

    for table in ("cloud_jobs", "cloud_workspaces", "cloud_artifacts", "cloud_job_events", "cloud_checkpoints"):
        _owner_rls(table)


def downgrade() -> None:
    for table in ("cloud_checkpoints", "cloud_job_events", "cloud_artifacts", "cloud_workspaces", "cloud_jobs"):
        op.drop_table(table)
