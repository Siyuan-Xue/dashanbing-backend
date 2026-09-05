"""Public facts and training-memory API payloads (no research identities/paths)."""

from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_serializer, field_validator

from app.services.results import ProductActionCounts, ProductActionType, ProductShotSummary


class AnalystMetrics(BaseModel):
    action_counts: ProductActionCounts = Field(default_factory=ProductActionCounts)
    shots: ProductShotSummary = Field(default_factory=ProductShotSummary)
    registered_participant_count: int = 0
    event_count: int = 0


class AnalystSubject(BaseModel):
    id: str
    label: str


class AnalystEvidence(BaseModel):
    id: str
    event_index: int
    subject_id: str | None
    action_type: ProductActionType
    start_ms: float
    end_ms: float
    time_ms: float
    media_kind: Literal["phases"] = "phases"
    times_ms: dict[str, float] = Field(default_factory=dict)
    result: Literal["make", "miss", "undetermined"] | None = None
    confidence: float | None = None
    angles: dict[str, float] = Field(default_factory=dict)


class AnalystFacts(BaseModel):
    schema_version: Literal[1] = 1
    metrics: AnalystMetrics = Field(default_factory=AnalystMetrics)
    subjects: list[AnalystSubject] = Field(default_factory=list)
    evidence: list[AnalystEvidence] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    pose_available: bool = False
    fingerprint: str = ""


class PublicDates(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    @field_serializer("created_at", "updated_at", "occurred_at", check_fields=False, when_used="json")
    def serialize_date(self, value: datetime) -> str:
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


class TrainingProfileCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["player", "team"]
    name: str = Field(min_length=1, max_length=120)
    goals: str = Field(default="", max_length=10000)
    notes: str = Field(default="", max_length=20000)

    @field_validator("name", mode="before")
    @classmethod
    def trim_name(cls, value):
        return value.strip() if isinstance(value, str) else value


class TrainingProfileUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str | None = Field(default=None, min_length=1, max_length=120)
    goals: str | None = Field(default=None, max_length=10000)
    notes: str | None = Field(default=None, max_length=20000)

    @field_validator("name", "goals", "notes", mode="before")
    @classmethod
    def supplied_fields_not_null(cls, value):
        if value is None:
            raise ValueError("Supplied fields cannot be null")
        return value

    @field_validator("name", mode="before")
    @classmethod
    def trim_name(cls, value):
        return value.strip() if isinstance(value, str) else value


class TrainingProfilePublic(PublicDates):
    id: str
    kind: Literal["player", "team"]
    name: str
    goals: str
    notes: str
    created_at: datetime
    updated_at: datetime


class ObservationPublic(PublicDates):
    id: str
    profile_id: str
    task_id: str | None
    occurred_at: datetime
    mode: Literal["quick", "full"]
    metrics: AnalystMetrics
    media_available: bool


class SubjectAssignment(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    profile_id: str | None = None


class ContextSubject(AnalystSubject):
    profile_id: str | None = None


class AnalystContextUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    subjects: list[SubjectAssignment] = Field(default_factory=list)
    team_profile_id: str | None = None
    comparison_id: str | None = None


class AnalystContext(BaseModel):
    task_id: str
    facts: AnalystFacts
    subjects: list[ContextSubject]
    team_profile_id: str | None = None
    comparison_id: str | None = None
    comparisons: list[ObservationPublic] = Field(default_factory=list)
