"""Public analyst report and conversation contracts, independent of video results."""
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


Locale = Literal["zh", "en"]
Style = Literal["coach", "roast"]


class ReportRequest(BaseModel):
    locale: Locale = "zh"
    style: Style = "coach"
    regenerate: bool = False
    subject_id: str | None = None


class ComparisonRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    locale: Locale = "zh"
    style: Style = "coach"
    regenerate: bool = False
    comparison_id: str = Field(min_length=1)


class ReportsRequest(BaseModel):
    locale: Locale = "zh"


class EvidenceComment(BaseModel):
    model_config = ConfigDict(extra="forbid")
    text: str = Field(min_length=1, max_length=3000)
    evidence_ids: list[str] = Field(default_factory=list, max_length=20)


class PlayerComment(EvidenceComment):
    subject_id: str


class ReportBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    summary: str = Field(min_length=1, max_length=3000)
    highlights: list[EvidenceComment] = Field(default_factory=list, max_length=12)
    players: list[PlayerComment] = Field(default_factory=list, max_length=30)
    comparison: EvidenceComment | None = None
    suggestions: list[str] = Field(default_factory=list, max_length=8)


class ReportPublic(ReportBody):
    id: str
    model: str
    locale: Locale
    style: Style
    created_at: datetime


class ReportState(BaseModel):
    status: Literal["disabled", "waiting", "queued", "running", "completed", "failed"]
    report: ReportPublic | None = None
    error: str | None = None


class ReportVariant(ReportState):
    subject_id: str | None = None
    locale: Locale
    style: Style


class ReportsCollection(BaseModel):
    items: list[ReportVariant] = Field(default_factory=list)
    facts: dict = Field(default_factory=dict)
    subjects: list[dict] = Field(default_factory=list)
    provenance: dict | None = None


class ComparisonReportState(ReportState):
    comparison_id: str


class ComparisonReports(BaseModel):
    items: list[ComparisonReportState] = Field(default_factory=list)


class ConversationCreate(BaseModel):
    task_id: str | None = None
    preset_id: str | None = None
    subject_id: str | None = None
    comparison_id: str | None = None
    locale: Locale = "zh"
    style: Style = "coach"

    @model_validator(mode="after")
    def one_source(self):
        if bool(self.task_id) == bool(self.preset_id):
            raise ValueError("Choose exactly one task or preset")
        return self


class MessageCreate(BaseModel):
    content: str = Field(min_length=1, max_length=4000)
    request_id: str = Field(min_length=1, max_length=100)

    @model_validator(mode="after")
    def trimmed_content(self):
        self.content = self.content.strip()
        if not self.content:
            raise ValueError("Message cannot be empty")
        return self


class MessagePublic(BaseModel):
    id: str
    role: Literal["user", "assistant"]
    content: str
    citations: list[str]
    status: Literal["queued", "running", "completed", "failed"]


class ConversationPublic(BaseModel):
    id: str
    messages: list[MessagePublic]


class MessageAccepted(BaseModel):
    message_id: str
    job_id: str
