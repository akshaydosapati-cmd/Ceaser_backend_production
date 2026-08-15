"""Add durable device command gateway.

Revision ID: 20260811_0026
Revises: 20260811_0025
"""

from alembic import op
import sqlalchemy as sa

revision = "20260811_0026"
down_revision = "20260811_0025"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("desktop_devices", sa.Column("gateway_session_id", sa.String(120)))
    op.add_column("desktop_devices", sa.Column("gateway_connected_at", sa.DateTime(timezone=True)))
    op.add_column("desktop_devices", sa.Column("gateway_last_heartbeat_at", sa.DateTime(timezone=True)))
    op.add_column("desktop_devices", sa.Column("gateway_disconnected_at", sa.DateTime(timezone=True)))
    op.add_column("desktop_devices", sa.Column("capabilities_json", sa.JSON(), nullable=False, server_default=sa.text("'[]'::json")))
    op.create_index("ix_desktop_devices_gateway_session_id", "desktop_devices", ["gateway_session_id"])
    op.create_table(
        "desktop_commands",
        sa.Column("id", sa.String(36), primary_key=True), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("device_id", sa.String(120), nullable=False), sa.Column("request_id", sa.String(120), nullable=False),
        sa.Column("task_id", sa.String(120), nullable=False), sa.Column("agent_id", sa.String(80), nullable=False),
        sa.Column("capability", sa.String(160), nullable=False), sa.Column("request_json", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(40), nullable=False), sa.Column("result_json", sa.JSON()), sa.Column("safe_error", sa.Text()),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False), sa.Column("delivered_at", sa.DateTime(timezone=True)),
        sa.Column("completed_at", sa.DateTime(timezone=True)), sa.Column("updated_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint("user_id", "request_id", name="uq_desktop_commands_user_request"),
    )
    for column in ("user_id", "device_id", "request_id", "task_id", "capability", "status", "expires_at"):
        op.create_index(f"ix_desktop_commands_{column}", "desktop_commands", [column])
    op.execute("alter table desktop_commands enable row level security")
    op.execute("create policy desktop_commands_owner_policy on desktop_commands using (user_id::text = auth.uid()::text) with check (user_id::text = auth.uid()::text)")


def downgrade() -> None:
    op.drop_table("desktop_commands")
    op.drop_index("ix_desktop_devices_gateway_session_id", table_name="desktop_devices")
    for column in ("capabilities_json", "gateway_disconnected_at", "gateway_last_heartbeat_at", "gateway_connected_at", "gateway_session_id"):
        op.drop_column("desktop_devices", column)
