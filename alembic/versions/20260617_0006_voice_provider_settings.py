"""voice provider settings

Revision ID: 20260617_0006
Revises: 20260617_0005
Create Date: 2026-06-17
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20260617_0006"
down_revision: Union[str, None] = "20260617_0005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("voice_settings", sa.Column("voice_provider", sa.String(length=32), nullable=False, server_default="auto"))
    op.alter_column("voice_settings", "voice_provider", server_default=None)


def downgrade() -> None:
    op.drop_column("voice_settings", "voice_provider")
