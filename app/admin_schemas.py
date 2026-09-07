"""Metadata-only administrator API types; unknown mutation fields are rejected."""
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator, field_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra='forbid')


class QuotaPatch(StrictModel):
    drafts: int | None = Field(default=None, ge=0)
    unfinished: int | None = Field(default=None, ge=0)
    daily_video: int | None = Field(default=None, ge=0)
    daily_ai: int | None = Field(default=None, ge=0)


class ReasonedMutation(StrictModel):
    reason: str = Field(min_length=3, max_length=500)

    @field_validator('reason', mode='before')
    @classmethod
    def trim_reason(cls, value):
        return value.strip() if isinstance(value, str) else value


class ForceLogout(ReasonedMutation):
    pass


class UserPatch(ReasonedMutation):
    is_active: bool | None = None
    quotas: QuotaPatch | None = None


class SettingsPatch(ReasonedMutation):
    video_enabled: bool | None = None
    video_paused: bool | None = None
    ai_enabled: bool | None = None
    ai_paused: bool | None = None
    ai_concurrency: int | None = Field(default=None, ge=1)
    default_quotas: QuotaPatch | None = None


class JobAction(ReasonedMutation):
    kind: Literal['video', 'ai', 'preset']
    ids: list[str] = Field(min_length=1, max_length=10)
    action: Literal['hold', 'release', 'priority', 'retry', 'backfill']
    priority: int | None = Field(default=None, ge=-100, le=100)

    @model_validator(mode='after')
    def valid_action(self):
        if len(set(self.ids)) != len(self.ids) or any(not item or len(item) > 100 for item in self.ids):
            raise ValueError('Job IDs must be unique and nonempty')
        if (self.action == 'priority') != (self.priority is not None):
            raise ValueError('priority is required only for the priority action')
        return self


class JobMetadata(BaseModel):
    id: str
    kind: Literal['video', 'ai', 'preset']
    owner_id: int | None = None
    task_id: str | None = None
    status: str
    created_at: datetime
    updated_at: datetime
    attempts: int
    held: bool
    priority: int
    admin_retries: int
    allowed_actions: list[str]


class JobPage(BaseModel):
    items: list[JobMetadata]
    total: int
    page: int
    page_size: int
