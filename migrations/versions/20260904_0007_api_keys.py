"""Add owner-scoped API key verifiers and lifecycle metadata."""

from alembic import op
import sqlalchemy as sa


revision = "20260904_0007"
down_revision = "20260904_0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "api_key",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("owner_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=80), nullable=False),
        sa.Column("digest", sa.String(length=64), nullable=False),
        sa.Column("prefix", sa.String(length=16), nullable=False),
        sa.Column("last_four", sa.String(length=4), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["owner_id"],
            ["user.id"],
            name="fk_api_key_owner_id_user",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_api_key_owner_id", "api_key", ["owner_id"], unique=False)
    op.create_index("ix_api_key_digest", "api_key", ["digest"], unique=True)
    op.create_index("ix_api_key_expires_at", "api_key", ["expires_at"], unique=False)
    op.create_index("ix_api_key_revoked_at", "api_key", ["revoked_at"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_api_key_revoked_at", table_name="api_key")
    op.drop_index("ix_api_key_expires_at", table_name="api_key")
    op.drop_index("ix_api_key_digest", table_name="api_key")
    op.drop_index("ix_api_key_owner_id", table_name="api_key")
    op.drop_table("api_key")
