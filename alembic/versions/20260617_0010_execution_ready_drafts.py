"""execution ready drafts

Revision ID: 20260617_0010
Revises: 20260617_0009
Create Date: 2026-06-17
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20260617_0010"
down_revision: Union[str, None] = "20260617_0009"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("drafts", sa.Column("target_app", sa.String(length=80), nullable=False, server_default="keep_as_draft"))
    op.add_column("drafts", sa.Column("requested_units", sa.Integer(), nullable=False, server_default="8"))
    op.create_index(op.f("ix_drafts_target_app"), "drafts", ["target_app"], unique=False)
    op.alter_column("drafts", "target_app", server_default=None)
    op.alter_column("drafts", "requested_units", server_default=None)


def downgrade() -> None:
    op.drop_index(op.f("ix_drafts_target_app"), table_name="drafts")
    op.drop_column("drafts", "requested_units")
    op.drop_column("drafts", "target_app")
