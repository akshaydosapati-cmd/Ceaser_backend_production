"""document extraction metadata

Revision ID: 20260617_0007
Revises: 20260617_0006
Create Date: 2026-06-17
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20260617_0007"
down_revision: Union[str, None] = "20260617_0006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("files", sa.Column("extracted_content_encrypted", sa.Text(), nullable=True))
    op.add_column("files", sa.Column("extraction_metadata_encrypted", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("files", "extraction_metadata_encrypted")
    op.drop_column("files", "extracted_content_encrypted")
