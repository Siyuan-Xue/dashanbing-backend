import { jsonInit, request } from "../workspace/api";
import type { Task } from "../workspace/types";

export const SYNC_CAMERAS = ["cam_01", "cam_02", "cam_03", "cam_04"] as const;
export type SyncCamera = typeof SYNC_CAMERAS[number];
export type CameraValues<T> = Record<SyncCamera, T>;
export type RegistrationFields = { enrollment_mode: "sequential" | "lineup"; expected_persons: number | null };
export type SyncStatus = "unconfirmed" | "confirmed" | "stale" | "legacy";
// Optional extensions work with both the existing and regenerated OpenAPI schema.
export type ConfigurableTask = Task & Partial<RegistrationFields> & { sync_status?: SyncStatus };
export type CameraPreview = {
  source_version: string; duration_ms: number; fps: number; frame_count: number;
  source_start_pts_ms: number; frame_timestamps_ms: number[]; video_url: string;
};
export type SyncPreview = {
  status: "unprepared" | "preparing" | "ready" | "failed";
  source_versions: CameraValues<string>; cameras: Partial<CameraValues<CameraPreview>>;
  error: { code?: string; message?: string } | string | null;
};
export type SyncFrame = {
  camera: SyncCamera; source_version: string; requested_time_ms: number; actual_time_ms: number;
  source_pts_ms: number; frame_index: number; image_data_url: string;
};
export type SyncConfig = {
  schema_version: 1; anchor_camera: "cam_03"; camera_time_offsets_ms: CameraValues<number>;
  selected_timestamps_ms: CameraValues<number> | null; input_versions: CameraValues<string>;
  durations_ms: CameraValues<number>; overlap_start_ms: number; overlap_end_ms: number; confirmed_at: string;
};
export type TaskSync = { status: SyncStatus; source_versions: CameraValues<string>; config: SyncConfig | null };
const base = (id: string) => `/api/v1/tasks/${encodeURIComponent(id)}/sync`;
export const taskSyncApi = {
  get: (id: string, signal?: AbortSignal) => request<TaskSync>(base(id), { signal }),
  prepare: (id: string, signal?: AbortSignal) => request<SyncPreview>(`${base(id)}/preview`, { ...jsonInit("POST"), signal }),
  preview: (id: string, signal?: AbortSignal) => request<SyncPreview>(`${base(id)}/preview`, { signal }),
  frame: (id: string, camera: SyncCamera, time: number, version: string, signal?: AbortSignal) => {
    const params = new URLSearchParams({ time_ms: String(time), source_version: version });
    return request<SyncFrame>(`${base(id)}/frames/${camera}?${params}`, { signal });
  },
  confirm: (id: string, inputVersions: CameraValues<string>, selected: CameraValues<number>) => request<TaskSync>(base(id), jsonInit("PUT", { input_versions: inputVersions, selected_timestamps_ms: selected })),
};

function nearestFrameIndex(timestamps: readonly number[], time: number) {
  let low = 0, high = timestamps.length - 1;
  while (low < high) {
    const middle = Math.floor((low + high) / 2);
    if (timestamps[middle] < time) low = middle + 1; else high = middle;
  }
  return low > 0 && time - timestamps[low - 1] <= timestamps[low] - time + 1e-9 ? low - 1 : low;
}
export function nearestFrameTime(timestamps: readonly number[], time: number) {
  return timestamps[nearestFrameIndex(timestamps, time)];
}
export function adjacentFrameTime(timestamps: readonly number[], time: number, direction: -1 | 1) {
  return timestamps[Math.max(0, Math.min(timestamps.length - 1, nearestFrameIndex(timestamps, time) + direction))];
}
// Local-only preview calculation; the backend validates and calculates persisted offsets.
export function alignmentFor(selected: CameraValues<number>, durations: CameraValues<number>) {
  if (SYNC_CAMERAS.some(camera => !Number.isFinite(selected[camera]) || !Number.isFinite(durations[camera]) || selected[camera] < 0 || selected[camera] >= durations[camera])) return null;
  const offsets = Object.fromEntries(SYNC_CAMERAS.map(camera => [camera, selected[camera] - selected.cam_03])) as CameraValues<number>;
  const start = Math.max(...SYNC_CAMERAS.map(camera => -offsets[camera]));
  const end = Math.min(...SYNC_CAMERAS.map(camera => durations[camera] - offsets[camera]));
  return end > start ? { offsets, start, end } : null;
}
