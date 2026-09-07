"""Persistent operations metadata. No user content is copied into these records."""
from datetime import datetime
from uuid import uuid4

from sqlalchemy import Column, Text
from sqlmodel import Field, SQLModel
from app.models import utc_now


class AdminSettings(SQLModel, table=True):
    __tablename__ = 'admin_settings'
    id: int = Field(default=1, primary_key=True)
    values_json: str = Field(default='{}', sa_column=Column(Text, nullable=False))


class AdminUserQuota(SQLModel, table=True):
    __tablename__ = 'admin_user_quota'
    owner_id: int = Field(primary_key=True, foreign_key='user.id')
    values_json: str = Field(default='{}', sa_column=Column(Text, nullable=False))


class AdminJobControl(SQLModel, table=True):
    __tablename__ = 'admin_job_control'
    kind: str = Field(primary_key=True)
    job_id: str = Field(primary_key=True)
    held: bool = False
    priority: int = 0
    admin_retries: int = 0
    repair: bool = False


class AdminRepairDay(SQLModel, table=True):
    __tablename__ = 'admin_repair_day'
    utc_date: str = Field(primary_key=True)
    video_used: int = 0
    ai_used: int = 0


class AdminLease(SQLModel, table=True):
    __tablename__ = 'admin_lease'
    kind: str = Field(primary_key=True)
    job_id: str = Field(primary_key=True)
    pool: str = Field(index=True)
    pid: int
    hostname: str
    created_at: datetime = Field(default_factory=utc_now)


class AdminAttempt(SQLModel, table=True):
    __tablename__ = 'admin_attempt'
    id: str = Field(default_factory=lambda: str(uuid4()), primary_key=True)
    kind: str
    job_id: str = Field(index=True)
    owner_id: int | None = Field(default=None, foreign_key='user.id', index=True)
    repair: bool = False
    created_at: datetime = Field(default_factory=utc_now, index=True)


class AdminAudit(SQLModel, table=True):
    __tablename__ = 'admin_audit'
    id: str = Field(default_factory=lambda: str(uuid4()), primary_key=True)
    actor_id: int = Field(foreign_key='user.id')
    action: str
    reason: str = Field(max_length=500)
    target_kind: str
    target_ids_json: str = '[]'
    changes_json: str = Field(default='{}', sa_column=Column(Text, nullable=False))
    created_at: datetime = Field(default_factory=utc_now, index=True)


class AdminPresetJob(SQLModel, table=True):
    __tablename__ = 'admin_preset_job'
    id: str = Field(primary_key=True)
    preset_id: str
    status: str = 'queued'
    attempts: int = 0
    expected: bool = True
    payload_json: str = Field(default='{}', sa_column=Column(Text, nullable=False))
    usage_json: str = '{}'
    available_at: datetime = Field(default_factory=utc_now)
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)
