"""Add user identity metadata and analysis ownership."""

import os

from alembic import op
import sqlalchemy as sa


revision = "20260904_0002"
down_revision = "20260903_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("user") as batch_op:
        batch_op.add_column(sa.Column("email", sa.String(length=255), nullable=True))
        batch_op.add_column(
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true())
        )
        batch_op.add_column(
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.text("CURRENT_TIMESTAMP"),
            )
        )
    op.create_index("ix_user_email", "user", ["email"], unique=True)

    with op.batch_alter_table("analysis") as batch_op:
        batch_op.add_column(sa.Column("owner_id", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True))
        batch_op.add_column(
            sa.Column("created_via", sa.String(length=32), nullable=False, server_default="legacy")
        )
        batch_op.add_column(
            sa.Column("retry_count", sa.Integer(), nullable=False, server_default="0")
        )

    bootstrap_username = os.getenv("BASKETBALL_ADMIN_USERNAME", "admin")
    connection = op.get_bind()
    bootstrap_owner_id = connection.execute(
        sa.text("SELECT id FROM user WHERE username = :username"),
        {"username": bootstrap_username},
    ).scalar_one_or_none()
    if bootstrap_owner_id is None:
        raise RuntimeError("Cannot backfill analyses because the bootstrap admin is missing")
    connection.execute(
        sa.text(
            "UPDATE analysis SET owner_id = :owner_id, submitted_at = created_at "
            "WHERE owner_id IS NULL"
        ),
        {"owner_id": bootstrap_owner_id},
    )

    with op.batch_alter_table("analysis") as batch_op:
        batch_op.alter_column("owner_id", existing_type=sa.Integer(), nullable=False)
        batch_op.create_foreign_key("fk_analysis_owner_id_user", "user", ["owner_id"], ["id"])
        batch_op.create_index("ix_analysis_owner_id", ["owner_id"], unique=False)


def downgrade() -> None:
    with op.batch_alter_table("analysis") as batch_op:
        batch_op.drop_index("ix_analysis_owner_id")
        batch_op.drop_constraint("fk_analysis_owner_id_user", type_="foreignkey")
        batch_op.drop_column("retry_count")
        batch_op.drop_column("created_via")
        batch_op.drop_column("submitted_at")
        batch_op.drop_column("owner_id")
    op.drop_index("ix_user_email", table_name="user")
    with op.batch_alter_table("user") as batch_op:
        batch_op.drop_column("created_at")
        batch_op.drop_column("is_active")
        batch_op.drop_column("email")
