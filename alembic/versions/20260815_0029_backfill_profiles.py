"""Create profile rows for existing users.

Revision ID: 20260815_0029
Revises: 20260815_0028
"""

from alembic import op


revision = "20260815_0029"
down_revision = "20260815_0028"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        INSERT INTO profiles (id, user_id, onboarding_completed)
        SELECT gen_random_uuid()::text, users.id, false
        FROM users
        WHERE NOT EXISTS (
            SELECT 1 FROM profiles WHERE profiles.user_id = users.id
        )
        """
    )


def downgrade() -> None:
    # Existing profile rows cannot be distinguished safely from newly edited rows.
    pass
