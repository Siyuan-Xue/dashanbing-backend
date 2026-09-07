"""Versioned public camera synchronization payloads (all times in milliseconds)."""
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, FiniteFloat, model_validator

Camera = Literal['cam_01', 'cam_02', 'cam_03', 'cam_04']
CAMERAS = ('cam_01', 'cam_02', 'cam_03', 'cam_04')
SyncStatus = Literal['unconfirmed', 'confirmed', 'stale', 'legacy']


class SyncInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    input_versions: dict[Camera, str] | None = None
    selected_timestamps_ms: dict[Camera, FiniteFloat] | None = None
    offsets_ms: dict[Camera, FiniteFloat] | None = None

    @model_validator(mode='after')
    def complete_representation(self):
        if (self.selected_timestamps_ms is None) == (self.offsets_ms is None):
            raise ValueError('Supply exactly one timestamp or offset map')
        values = self.selected_timestamps_ms if self.selected_timestamps_ms is not None else self.offsets_ms
        if set(values) != set(CAMERAS):
            raise ValueError('All four cameras are required')
        if self.input_versions is not None and (set(self.input_versions) != set(CAMERAS) or
                                                any(not v or len(v) > 128 for v in self.input_versions.values())):
            raise ValueError('All four source versions are required')
        return self


class SyncConfig(BaseModel):
    schema_version: Literal[1] = 1
    anchor_camera: Literal['cam_03'] = 'cam_03'
    camera_time_offsets_ms: dict[Camera, FiniteFloat]
    selected_timestamps_ms: dict[Camera, FiniteFloat] | None = None
    input_versions: dict[Camera, str]
    durations_ms: dict[Camera, FiniteFloat]
    overlap_start_ms: FiniteFloat
    overlap_end_ms: FiniteFloat
    confirmed_at: str


class SyncPublic(BaseModel):
    status: SyncStatus
    source_versions: dict[Camera, str]
    config: SyncConfig | None = None


class PreviewCamera(BaseModel):
    source_version: str
    duration_ms: float
    fps: float
    frame_count: int
    source_start_pts_ms: float
    frame_timestamps_ms: list[float]
    video_url: str


class PreviewStatus(BaseModel):
    status: Literal['unprepared', 'preparing', 'ready', 'failed']
    source_versions: dict[Camera, str]
    cameras: dict[Camera, PreviewCamera] = Field(default_factory=dict)
    error: dict[str, str] | None = None


class FramePublic(BaseModel):
    camera: Camera
    source_version: str
    requested_time_ms: float
    actual_time_ms: float
    source_pts_ms: float
    frame_index: int
    image_data_url: str
