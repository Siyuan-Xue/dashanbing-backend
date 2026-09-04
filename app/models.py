from datetime import datetime, timezone
from typing import Literal
from uuid import uuid4

from pydantic import field_serializer, field_validator
from sqlalchemy import Column, Text
from sqlmodel import Field, SQLModel


class User(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    username: str = Field(index=True, unique=True, min_length=3, max_length=50)
    email: str | None = Field(default=None, index=True, unique=True, max_length=255)
    hashed_password: str
    is_active: bool = Field(default=True, nullable=False)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), nullable=False)


class UserRegistration(SQLModel):
    username: str = Field(min_length=3, max_length=50)
    email: str = Field(min_length=3, max_length=255)
    password: str = Field(min_length=8, max_length=128)

    @field_validator("username", "email", mode="before")
    @classmethod
    def normalize_identity_fields(cls, value: str) -> str:
        return value.strip().casefold()


class UserPublic(SQLModel):
    id: int
    username: str
    email: str | None
    is_active: bool


class Token(SQLModel):
    access_token: str
    token_type: str


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class Analysis(SQLModel, table=True):
    id: str = Field(default_factory=lambda: str(uuid4()), primary_key=True)
    title: str = Field(min_length=1, max_length=120)
    mode: str = Field(default="full", max_length=16)
    source_type: str = Field(default="upload", max_length=16)
    preset_id: str | None = Field(default=None, max_length=64)
    status: str = Field(default="queued", index=True, max_length=32)
    progress: int = Field(default=0, ge=0, le=100)
    stage_message: str = Field(default="等待执行", max_length=255)
    input_manifest_json: str = Field(sa_column=Column(Text, nullable=False))
    owner_id: int = Field(foreign_key="user.id", nullable=False, index=True)
    submitted_at: datetime | None = Field(default_factory=utc_now, index=True)
    created_via: str = Field(default="legacy", max_length=32)
    retry_count: int = Field(default=0, ge=0)
    error_code: str | None = Field(default=None, max_length=64)
    error_message: str | None = Field(default=None, sa_column=Column(Text, nullable=True))
    created_at: datetime = Field(default_factory=utc_now, index=True)
    updated_at: datetime = Field(default_factory=utc_now)
    started_at: datetime | None = None
    completed_at: datetime | None = None


class AnalysisPublic(SQLModel):
    id: str
    title: str
    mode: str
    source_type: str
    preset_id: str | None
    status: str
    progress: int
    stage_message: str
    error_code: str | None
    error_message: str | None
    owner_id: int
    submitted_at: datetime | None
    created_via: str
    retry_count: int
    created_at: datetime
    updated_at: datetime
    started_at: datetime | None
    completed_at: datetime | None

    @field_serializer(
        "created_at",
        "updated_at",
        "submitted_at",
        "started_at",
        "completed_at",
        when_used="json",
    )
    def serialize_utc_datetime(self, value: datetime | None) -> str | None:
        if value is None:
            return None
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


class PresetRerunRequest(SQLModel):
    preset_id: str
    mode: Literal["quick", "full"] = "full"


class PresetPublic(SQLModel):
    id: str
    title: str
    description: str
    expected_minutes: float
