"""Add CEASER agent automation system.

Revision ID: 20260621_0012
Revises: 20260620_0011
Create Date: 2026-06-21
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision: str = "20260621_0012"
down_revision: str | None = "20260620_0011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "automation_templates",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("category", sa.String(length=80), nullable=False),
        sa.Column("description", sa.String(length=1200), nullable=False),
        sa.Column("default_agent", sa.String(length=80), nullable=False),
        sa.Column("default_prompt", sa.Text(), nullable=False),
        sa.Column("supported_frequencies", sa.JSON(), nullable=False),
        sa.Column("icon", sa.String(length=80), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_automation_templates_category", "automation_templates", ["category"])

    op.create_table(
        "automations",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("workspace_id", sa.String(length=36), nullable=True),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.String(length=2000), nullable=True),
        sa.Column("automation_type", sa.String(length=80), nullable=False),
        sa.Column("assigned_agent", sa.String(length=80), nullable=False),
        sa.Column("trigger_frequency", sa.String(length=80), nullable=False),
        sa.Column("trigger_time", sa.String(length=20), nullable=True),
        sa.Column("timezone", sa.String(length=80), nullable=False),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("config_json", sa.JSON(), nullable=False),
        sa.Column("last_run_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("next_run_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_automations_user_id", "automations", ["user_id"])
    op.create_index("ix_automations_workspace_id", "automations", ["workspace_id"])
    op.create_index("ix_automations_automation_type", "automations", ["automation_type"])
    op.create_index("ix_automations_assigned_agent", "automations", ["assigned_agent"])
    op.create_index("ix_automations_status", "automations", ["status"])
    op.create_index("ix_automations_next_run_at", "automations", ["next_run_at"])

    op.create_table(
        "automation_runs",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("automation_id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("workspace_id", sa.String(length=36), nullable=True),
        sa.Column("assigned_agent", sa.String(length=80), nullable=False),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("output_title", sa.String(length=255), nullable=True),
        sa.Column("output_summary", sa.String(length=2000), nullable=True),
        sa.Column("output_content_encrypted", sa.Text(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("metadata_json", sa.JSON(), nullable=False),
        sa.ForeignKeyConstraint(["automation_id"], ["automations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_automation_runs_automation_id", "automation_runs", ["automation_id"])
    op.create_index("ix_automation_runs_user_id", "automation_runs", ["user_id"])
    op.create_index("ix_automation_runs_workspace_id", "automation_runs", ["workspace_id"])
    op.create_index("ix_automation_runs_assigned_agent", "automation_runs", ["assigned_agent"])
    op.create_index("ix_automation_runs_status", "automation_runs", ["status"])


def downgrade() -> None:
    op.drop_index("ix_automation_runs_status", table_name="automation_runs")
    op.drop_index("ix_automation_runs_assigned_agent", table_name="automation_runs")
    op.drop_index("ix_automation_runs_workspace_id", table_name="automation_runs")
    op.drop_index("ix_automation_runs_user_id", table_name="automation_runs")
    op.drop_index("ix_automation_runs_automation_id", table_name="automation_runs")
    op.drop_table("automation_runs")

    op.drop_index("ix_automations_next_run_at", table_name="automations")
    op.drop_index("ix_automations_status", table_name="automations")
    op.drop_index("ix_automations_assigned_agent", table_name="automations")
    op.drop_index("ix_automations_automation_type", table_name="automations")
    op.drop_index("ix_automations_workspace_id", table_name="automations")
    op.drop_index("ix_automations_user_id", table_name="automations")
    op.drop_table("automations")

    op.drop_index("ix_automation_templates_category", table_name="automation_templates")
    op.drop_table("automation_templates")
