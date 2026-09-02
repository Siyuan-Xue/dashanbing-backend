"""Initial local product schema."""

from alembic import op
import sqlalchemy as sa


revision = "20260903_0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "user",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("username", sa.String(length=50), nullable=False),
        sa.Column("hashed_password", sa.String(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("username"),
    )
    op.create_index("ix_user_username", "user", ["username"], unique=True)
    op.create_table(
        "analysis",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("title", sa.String(length=120), nullable=False),
        sa.Column("mode", sa.String(length=16), nullable=False),
        sa.Column("source_type", sa.String(length=16), nullable=False),
        sa.Column("preset_id", sa.String(length=64), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("progress", sa.Integer(), nullable=False),
        sa.Column("stage_message", sa.String(length=255), nullable=False),
        sa.Column("input_manifest_json", sa.Text(), nullable=False),
        sa.Column("error_code", sa.String(length=64), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("started_at", sa.DateTime(), nullable=True),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_analysis_status", "analysis", ["status"], unique=False)
    op.create_index("ix_analysis_created_at", "analysis", ["created_at"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_analysis_created_at", table_name="analysis")
    op.drop_index("ix_analysis_status", table_name="analysis")
    op.drop_table("analysis")
    op.drop_index("ix_user_username", table_name="user")
    op.drop_table("user")
