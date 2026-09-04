"""Record staged upload operations for crash recovery."""

from alembic import op
import sqlalchemy as sa


revision = "20260904_0006"
down_revision = "20260904_0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "task_input",
        sa.Column("upload_operation_id", sa.String(length=32), nullable=True),
    )


def downgrade() -> None:
    with op.batch_alter_table("task_input") as batch_op:
        batch_op.drop_column("upload_operation_id")
