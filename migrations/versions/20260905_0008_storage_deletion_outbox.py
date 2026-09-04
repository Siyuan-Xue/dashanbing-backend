"""Add durable fixed-target filesystem deletion outbox."""

from alembic import op
import sqlalchemy as sa


revision = "20260905_0008"
down_revision = "20260904_0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "storage_deletion",
        sa.Column("analysis_id", sa.String(), nullable=False),
        sa.Column("target", sa.String(length=32), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("analysis_id", "target"),
    )


def downgrade() -> None:
    op.drop_table("storage_deletion")
