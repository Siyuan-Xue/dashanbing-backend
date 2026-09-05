"""Durable analyst and manually confirmed training memory records."""

from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import CheckConstraint, Column, Text, UniqueConstraint
from sqlmodel import Field, SQLModel


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def new_id() -> str:
    return str(uuid4())


class TrainingProfile(SQLModel, table=True):
    __tablename__ = "training_profile"
    __table_args__ = (CheckConstraint("kind IN ('player', 'team')", name="ck_training_profile_kind"),)

    id: str = Field(default_factory=new_id, primary_key=True)
    owner_id: int = Field(foreign_key="user.id", index=True)
    kind: str
    name: str = Field(max_length=120)
    goals: str = Field(default="", sa_column=Column(Text, nullable=False))
    notes: str = Field(default="", sa_column=Column(Text, nullable=False))
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class TaskSubject(SQLModel, table=True):
    __tablename__ = "task_subject"

    task_id: str = Field(foreign_key="analysis.id", ondelete="CASCADE", primary_key=True)
    subject_id: str = Field(primary_key=True)
    owner_id: int = Field(foreign_key="user.id", index=True)
    profile_id: str | None = Field(default=None, foreign_key="training_profile.id", ondelete="SET NULL", index=True)
    label: str = ""
    # Reserved __team__ row stores task-level team and comparison preferences.
    selected_comparison_id: str | None = Field(default=None, foreign_key="training_observation.id", ondelete="SET NULL")


class TrainingObservation(SQLModel, table=True):
    __tablename__ = "training_observation"
    __table_args__ = (UniqueConstraint("owner_id", "profile_id", "fingerprint", "mode", name="uq_training_observation_source_mode"),)

    id: str = Field(default_factory=new_id, primary_key=True)
    owner_id: int = Field(foreign_key="user.id", index=True)
    profile_id: str = Field(foreign_key="training_profile.id", ondelete="CASCADE", index=True)
    task_id: str | None = Field(default=None, index=True)
    source_task_id: str = Field(index=True)
    # Each source retains its own metrics/date and whether media still exists.
    # This makes deleting the latest rerun restore the other confirmed source.
    sources_json: str = Field(default="{}", sa_column=Column(Text, nullable=False))
    fingerprint: str = Field(index=True)
    occurred_at: datetime = Field(default_factory=utc_now)
    mode: str
    metrics_json: str = Field(default="{}", sa_column=Column(Text, nullable=False))


class AnalystReport(SQLModel, table=True):
    __tablename__ = "analyst_report"
    __table_args__ = (
        CheckConstraint("status IN ('queued', 'running', 'completed', 'failed')", name="ck_analyst_report_status"),
        CheckConstraint("kind IN ('session', 'comparison')", name="ck_analyst_report_kind"),
    )

    id: str = Field(default_factory=new_id, primary_key=True)
    owner_id: int = Field(foreign_key="user.id", index=True)
    task_id: str | None = Field(default=None, index=True)
    preset_id: str | None = None
    kind: str = "session"
    subject_id: str | None = Field(default=None, index=True)
    # Snapshot identity; memory revocation explicitly removes dependent reports.
    comparison_id: str | None = None
    cache_key: str = Field(unique=True, index=True)
    status: str = "queued"
    locale: str = "zh"
    style: str = "coach"
    model: str = ""
    body_json: str = Field(default="{}", sa_column=Column(Text, nullable=False))
    error: str | None = Field(default=None, sa_column=Column(Text, nullable=True))
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class AnalystConversation(SQLModel, table=True):
    __tablename__ = "analyst_conversation"

    id: str = Field(default_factory=new_id, primary_key=True)
    owner_id: int = Field(foreign_key="user.id", index=True)
    task_id: str | None = Field(default=None, index=True)
    preset_id: str | None = None
    subject_id: str | None = None
    comparison_id: str | None = None
    locale: str = "zh"
    style: str = "coach"
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class AnalystMessage(SQLModel, table=True):
    __tablename__ = "analyst_message"
    __table_args__ = (CheckConstraint("status IN ('queued', 'running', 'completed', 'failed')", name="ck_analyst_message_status"),)

    id: str = Field(default_factory=new_id, primary_key=True)
    conversation_id: str = Field(foreign_key="analyst_conversation.id", ondelete="CASCADE", index=True)
    owner_id: int = Field(foreign_key="user.id", index=True)
    role: str
    content: str = Field(default="", sa_column=Column(Text, nullable=False))
    citations_json: str = Field(default="[]", sa_column=Column(Text, nullable=False))
    status: str = "queued"
    revision: int = 0
    request_id: str | None = None
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class AnalystJob(SQLModel, table=True):
    __tablename__ = "analyst_job"
    __table_args__ = (
        CheckConstraint("kind IN ('prepare', 'report', 'message')", name="ck_analyst_job_kind"),
        CheckConstraint("status IN ('queued', 'running', 'completed', 'failed')", name="ck_analyst_job_status"),
    )

    id: str = Field(default_factory=new_id, primary_key=True)
    owner_id: int = Field(foreign_key="user.id", index=True)
    kind: str
    task_id: str | None = Field(default=None, index=True)
    report_id: str | None = Field(default=None, index=True)
    message_id: str | None = Field(default=None, index=True)
    request_id: str | None = Field(default=None, unique=True)
    status: str = "queued"
    attempts: int = 0
    payload_json: str = Field(default="{}", sa_column=Column(Text, nullable=False))
    usage_json: str = Field(default="{}", sa_column=Column(Text, nullable=False))
    error: str | None = Field(default=None, sa_column=Column(Text, nullable=True))
    available_at: datetime = Field(default_factory=utc_now, index=True)
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class AnalystProviderState(SQLModel, table=True):
    """One durable provider-wide deadline, independent of user/task cleanup."""
    __tablename__ = "analyst_provider_state"

    provider: str = Field(primary_key=True)
    available_at: datetime = Field(default_factory=utc_now)
