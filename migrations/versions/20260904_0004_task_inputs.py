"""Add durable staged task input metadata."""

from alembic import op
import sqlalchemy as sa


revision = "20260904_0004"
down_revision = "20260904_0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "task_input",
        sa.Column("task_id", sa.String(), nullable=False),
        sa.Column("slot", sa.String(length=32), nullable=False),
        sa.Column("original_filename", sa.String(length=255), nullable=False),
        sa.Column("byte_size", sa.Integer(), nullable=False),
        sa.Column("validation_state", sa.String(length=32), nullable=False),
        sa.Column("path", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["task_id"],
            ["analysis.id"],
            name="fk_task_input_task_id_analysis",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("task_id", "slot"),
    )


def downgrade() -> None:
    op.drop_table("task_input")
