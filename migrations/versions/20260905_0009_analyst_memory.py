"""Add durable analyst queue, conversations and confirmed training memory."""

from alembic import op
import sqlalchemy as sa


revision = "20260905_0009"
down_revision = "20260905_0008"
branch_labels = None
depends_on = None


def _created():
    return sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP"))


def _updated():
    return sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP"))


def upgrade() -> None:
    # Explicit historical definitions: never import the application's current models.
    op.create_table(
        "training_profile",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("owner_id", sa.Integer(), sa.ForeignKey("user.id"), nullable=False),
        sa.Column("kind", sa.String(), nullable=False),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("goals", sa.Text(), nullable=False, server_default=""),
        sa.Column("notes", sa.Text(), nullable=False, server_default=""),
        _created(), _updated(),
        sa.CheckConstraint("kind IN ('player', 'team')", name="ck_training_profile_kind"),
    )
    op.create_table(
        "training_observation",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("owner_id", sa.Integer(), sa.ForeignKey("user.id"), nullable=False),
        sa.Column("profile_id", sa.String(), sa.ForeignKey("training_profile.id", ondelete="CASCADE"), nullable=False),
        sa.Column("task_id", sa.String(), nullable=True),
        sa.Column("source_task_id", sa.String(), nullable=False),
        sa.Column("sources_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("fingerprint", sa.String(), nullable=False),
        sa.Column("occurred_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("mode", sa.String(), nullable=False),
        sa.Column("metrics_json", sa.Text(), nullable=False, server_default="{}"),
        sa.UniqueConstraint("owner_id", "profile_id", "fingerprint", "mode", name="uq_training_observation_source_mode"),
    )
    op.create_table(
        "task_subject",
        sa.Column("task_id", sa.String(), sa.ForeignKey("analysis.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("subject_id", sa.String(), primary_key=True),
        sa.Column("owner_id", sa.Integer(), sa.ForeignKey("user.id"), nullable=False),
        sa.Column("profile_id", sa.String(), sa.ForeignKey("training_profile.id", ondelete="SET NULL"), nullable=True),
        sa.Column("label", sa.String(), nullable=False, server_default=""),
        sa.Column("selected_comparison_id", sa.String(), sa.ForeignKey("training_observation.id", ondelete="SET NULL"), nullable=True),
    )
    op.create_table(
        "analyst_report",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("owner_id", sa.Integer(), sa.ForeignKey("user.id"), nullable=False),
        sa.Column("task_id", sa.String(), nullable=True),
        sa.Column("preset_id", sa.String(), nullable=True),
        sa.Column("cache_key", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False, server_default="queued"),
        sa.Column("locale", sa.String(), nullable=False, server_default="zh"),
        sa.Column("style", sa.String(), nullable=False, server_default="coach"),
        sa.Column("model", sa.String(), nullable=False, server_default=""),
        sa.Column("body_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("error", sa.Text(), nullable=True),
        _created(), _updated(),
        sa.CheckConstraint("status IN ('queued', 'running', 'completed', 'failed')", name="ck_analyst_report_status"),
    )
    op.create_table(
        "analyst_conversation",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("owner_id", sa.Integer(), sa.ForeignKey("user.id"), nullable=False),
        sa.Column("task_id", sa.String(), nullable=True),
        sa.Column("preset_id", sa.String(), nullable=True),
        sa.Column("subject_id", sa.String(), nullable=True),
        sa.Column("comparison_id", sa.String(), nullable=True),
        sa.Column("locale", sa.String(), nullable=False, server_default="zh"),
        sa.Column("style", sa.String(), nullable=False, server_default="coach"),
        _created(), _updated(),
    )
    op.create_table(
        "analyst_message",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("conversation_id", sa.String(), sa.ForeignKey("analyst_conversation.id", ondelete="CASCADE"), nullable=False),
        sa.Column("owner_id", sa.Integer(), sa.ForeignKey("user.id"), nullable=False),
        sa.Column("role", sa.String(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False, server_default=""),
        sa.Column("citations_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("status", sa.String(), nullable=False, server_default="queued"),
        sa.Column("revision", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("request_id", sa.String(), nullable=True),
        _created(), _updated(),
        sa.CheckConstraint("status IN ('queued', 'running', 'completed', 'failed')", name="ck_analyst_message_status"),
    )
    op.create_table(
        "analyst_job",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("owner_id", sa.Integer(), sa.ForeignKey("user.id"), nullable=False),
        sa.Column("kind", sa.String(), nullable=False),
        sa.Column("task_id", sa.String(), nullable=True),
        sa.Column("report_id", sa.String(), nullable=True),
        sa.Column("message_id", sa.String(), nullable=True),
        sa.Column("request_id", sa.String(), nullable=True),
        sa.Column("status", sa.String(), nullable=False, server_default="queued"),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("payload_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("usage_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("available_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        _created(), _updated(),
        sa.UniqueConstraint("request_id"),
        sa.CheckConstraint("kind IN ('prepare', 'report', 'message')", name="ck_analyst_job_kind"),
        sa.CheckConstraint("status IN ('queued', 'running', 'completed', 'failed')", name="ck_analyst_job_status"),
    )
    for table, columns in (
        ("training_profile", ("owner_id",)),
        ("training_observation", ("owner_id", "profile_id", "task_id", "source_task_id", "fingerprint")),
        ("task_subject", ("owner_id", "profile_id")),
        ("analyst_report", ("owner_id", "task_id")),
        ("analyst_conversation", ("owner_id", "task_id")),
        ("analyst_message", ("conversation_id", "owner_id")),
        ("analyst_job", ("owner_id", "task_id", "report_id", "message_id", "available_at")),
    ):
        for column in columns:
            op.create_index(f"ix_{table}_{column}", table, [column])
    op.create_index("ix_analyst_report_cache_key", "analyst_report", ["cache_key"], unique=True)


def downgrade() -> None:
    for table in ("analyst_job", "analyst_message", "analyst_conversation", "analyst_report",
                  "task_subject", "training_observation", "training_profile"):
        op.drop_table(table)
