"""security encryption and audit logs

Revision ID: 20260616_0003
Revises: 20260614_0002
Create Date: 2026-06-16
"""

from collections.abc import Sequence
import json

import sqlalchemy as sa
from alembic import op

from app.core.security.encryption import encrypt_json, encrypt_text

revision: str = "20260616_0003"
down_revision: str | None = "20260614_0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _encrypt_existing(table_name: str) -> None:
    connection = op.get_bind()
    rows = connection.execute(sa.text(f"SELECT id, content, metadata FROM {table_name}")).mappings().all()
    for row in rows:
        encrypted_content = encrypt_text(row["content"] or "")
        metadata = row["metadata"] or {}
        if isinstance(metadata, str):
            metadata = json.loads(metadata)
        encrypted_metadata = encrypt_json(metadata)
        connection.execute(
            sa.text(
                f"""
                UPDATE {table_name}
                SET content_encrypted = :content_encrypted,
                    metadata_encrypted = :metadata_encrypted,
                    content = :content,
                    metadata = :metadata
                WHERE id = :id
                """
            ),
            {
                "id": row["id"],
                "content_encrypted": encrypted_content,
                "metadata_encrypted": encrypted_metadata,
                "content": "[encrypted]",
                "metadata": "{}",
            },
        )


def upgrade() -> None:
    op.add_column("messages", sa.Column("content_encrypted", sa.String(), nullable=True))
    op.add_column("messages", sa.Column("metadata_encrypted", sa.String(), nullable=True))
    op.add_column("memories", sa.Column("content_encrypted", sa.String(), nullable=True))
    op.add_column("memories", sa.Column("metadata_encrypted", sa.String(), nullable=True))

    _encrypt_existing("messages")
    _encrypt_existing("memories")

    op.create_table(
        "audit_logs",
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("workspace_id", sa.String(length=36), nullable=True),
        sa.Column("action", sa.String(length=120), nullable=False),
        sa.Column("resource_type", sa.String(length=120), nullable=False),
        sa.Column("resource_id", sa.String(length=36), nullable=True),
        sa.Column("metadata", sa.JSON(), nullable=False),
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_audit_logs_user_id"), "audit_logs", ["user_id"])
    op.create_index(op.f("ix_audit_logs_workspace_id"), "audit_logs", ["workspace_id"])
    op.create_index(op.f("ix_audit_logs_action"), "audit_logs", ["action"])
    op.create_index(op.f("ix_audit_logs_resource_id"), "audit_logs", ["resource_id"])


def downgrade() -> None:
    op.drop_index(op.f("ix_audit_logs_resource_id"), table_name="audit_logs")
    op.drop_index(op.f("ix_audit_logs_action"), table_name="audit_logs")
    op.drop_index(op.f("ix_audit_logs_workspace_id"), table_name="audit_logs")
    op.drop_index(op.f("ix_audit_logs_user_id"), table_name="audit_logs")
    op.drop_table("audit_logs")
    op.drop_column("memories", "metadata_encrypted")
    op.drop_column("memories", "content_encrypted")
    op.drop_column("messages", "metadata_encrypted")
    op.drop_column("messages", "content_encrypted")
