"""Add personal report scope and the task's initial report language."""
from alembic import op
import sqlalchemy as sa

revision = "20260905_0011"
down_revision = "20260905_0010"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("analysis", sa.Column("analyst_locale", sa.String(2), nullable=False, server_default="zh"))
    op.add_column("analyst_report", sa.Column("subject_id", sa.String(), nullable=True))
    op.create_index("ix_analyst_report_subject_id", "analyst_report", ["subject_id"])
    op.create_table("analyst_provider_state", sa.Column("provider", sa.String(), primary_key=True), sa.Column("available_at", sa.DateTime(), nullable=False))


def downgrade():
    op.drop_table("analyst_provider_state")
    op.drop_index("ix_analyst_report_subject_id", "analyst_report")
    with op.batch_alter_table("analyst_report") as batch:
        batch.drop_column("subject_id")
    with op.batch_alter_table("analysis") as batch:
        batch.drop_column("analyst_locale")
