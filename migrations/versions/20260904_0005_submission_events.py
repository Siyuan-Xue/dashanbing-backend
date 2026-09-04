"""Add immutable submission events for durable daily quotas."""

from alembic import op
import sqlalchemy as sa


revision = "20260904_0005"
down_revision = "20260904_0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "submission_event",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("task_id", sa.String(), nullable=False),
        sa.Column("owner_id", sa.Integer(), nullable=False),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["owner_id"],
            ["user.id"],
            name="fk_submission_event_owner_id_user",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_submission_event_task_id",
        "submission_event",
        ["task_id"],
        unique=False,
    )
    op.create_index(
        "ix_submission_event_owner_id",
        "submission_event",
        ["owner_id"],
        unique=False,
    )
    op.create_index(
        "ix_submission_event_submitted_at",
        "submission_event",
        ["submitted_at"],
        unique=False,
    )
    connection = op.get_bind()
    connection.execute(
        sa.text(
            """
            INSERT INTO submission_event (task_id, owner_id, kind, submitted_at)
            SELECT id, owner_id, 'initial', submitted_at
            FROM analysis
            WHERE submitted_at IS NOT NULL
            """
        )
    )


def downgrade() -> None:
    op.drop_index("ix_submission_event_submitted_at", table_name="submission_event")
    op.drop_index("ix_submission_event_owner_id", table_name="submission_event")
    op.drop_index("ix_submission_event_task_id", table_name="submission_event")
    op.drop_table("submission_event")
