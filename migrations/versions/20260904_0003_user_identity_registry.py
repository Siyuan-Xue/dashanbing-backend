"""Enforce global normalized user identities."""

from alembic import op
import sqlalchemy as sa

from app.security import normalize_identity


revision = "20260904_0003"
down_revision = "20260904_0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "user_identity",
        sa.Column("value", sa.String(length=255), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["user.id"], name="fk_user_identity_user_id_user"),
        sa.PrimaryKeyConstraint("value"),
    )
    op.create_index("ix_user_identity_user_id", "user_identity", ["user_id"], unique=False)

    connection = op.get_bind()
    assigned: dict[str, int] = {}
    users = connection.execute(sa.text("SELECT id, username, email FROM user")).mappings()
    for user in users:
        for raw_value in (user["username"], user["email"]):
            if raw_value is None:
                continue
            value = normalize_identity(raw_value)
            prior_owner = assigned.get(value)
            if prior_owner is not None and prior_owner != user["id"]:
                raise RuntimeError(
                    "Cannot create global user identities because existing users collide after normalization"
                )
            if prior_owner == user["id"]:
                continue
            assigned[value] = user["id"]
            connection.execute(
                sa.text("INSERT INTO user_identity (value, user_id) VALUES (:value, :user_id)"),
                {"value": value, "user_id": user["id"]},
            )


def downgrade() -> None:
    op.drop_index("ix_user_identity_user_id", table_name="user_identity")
    op.drop_table("user_identity")
