"""Separate requested comparisons from the original session report."""
from alembic import op
import sqlalchemy as sa

revision = "20260905_0010"
down_revision = "20260905_0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Keep existing report bodies, cache keys, IDs and their queued jobs intact.
    op.add_column("analyst_report", sa.Column(
        "kind", sa.String(), sa.CheckConstraint("kind IN ('session', 'comparison')", name="ck_analyst_report_kind"),
        nullable=False, server_default="session",
    ))
    op.add_column("analyst_report", sa.Column("comparison_id", sa.String(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("analyst_report") as batch:
        batch.drop_constraint("ck_analyst_report_kind", type_="check")
        batch.drop_column("comparison_id")
        batch.drop_column("kind")
