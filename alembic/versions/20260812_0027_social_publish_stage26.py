"""stage26 durable social publish confirmation"""
from alembic import op
import sqlalchemy as sa
revision="20260812_0027";down_revision="20260811_0026";branch_labels=None;depends_on=None
def upgrade():
 op.create_table("social_publish_tasks",sa.Column("id",sa.String(36),primary_key=True),sa.Column("user_id",sa.String(36),sa.ForeignKey("users.id",ondelete="CASCADE"),nullable=False),sa.Column("task_id",sa.String(120),nullable=False,unique=True),sa.Column("device_id",sa.String(120),nullable=False),sa.Column("platform",sa.String(80),nullable=False),sa.Column("status",sa.String(40),nullable=False),sa.Column("draft_encrypted",sa.Text(),nullable=False),sa.Column("browser_session_id",sa.String(120)),sa.Column("expires_at",sa.DateTime(timezone=True),nullable=False),sa.Column("published_request_id",sa.String(120)),sa.Column("created_at",sa.DateTime(timezone=True),nullable=False),sa.Column("updated_at",sa.DateTime(timezone=True),nullable=False));op.create_index("ix_social_publish_tasks_user_id","social_publish_tasks",["user_id"]);op.create_index("ix_social_publish_tasks_status","social_publish_tasks",["status"])
def downgrade():op.drop_index("ix_social_publish_tasks_status",table_name="social_publish_tasks");op.drop_index("ix_social_publish_tasks_user_id",table_name="social_publish_tasks");op.drop_table("social_publish_tasks")
