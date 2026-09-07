// Contract-only test server state shared by legacy Vitest and Playwright uploads.
// Media is a generated 0.4-second, 25fps solid-color clip; no user data is read.
import { legacyFrameImage, legacyPreviewVideo } from "./legacySyncMediaFixture";
import type { CameraValues, SyncConfig, SyncStatus } from "../lib/task-sync";

const cameras = ["cam_01", "cam_02", "cam_03", "cam_04"] as const;
const slots = ["enrollment_video", ...cameras];
export const incompleteRegistration = { enrollment_mode: "sequential" as const, expected_persons: null, sync_status: "unconfirmed" as const };
// Use only for an already-uploaded, previously-confirmed draft, never an upload response.
export const confirmedRegistration = { enrollment_mode: "sequential" as const, expected_persons: 2, sync_status: "confirmed" as const };
export function submissionFixtureError(task: { status: string; expected_persons?: number | null; enrollment_mode?: string; sync_status?: string; inputs: { slot: string; validation_state: string }[] }) {
  if (task.status !== "draft") return { code: "task_state_conflict", message: "Only draft tasks can be submitted." };
  if (!Number.isInteger(task.expected_persons) || task.expected_persons! < 1 || task.expected_persons! > 6 || !["sequential", "lineup"].includes(task.enrollment_mode || "")) return { code: "registration_config_required", message: "Choose a registration method and person count." };
  if (slots.some(slot => !task.inputs.some(input => input.slot === slot && input.validation_state === "valid"))) return { code: "input_missing", message: "All five valid input files are required." };
  if (task.sync_status !== "confirmed") return { code: task.sync_status === "stale" ? "sync_stale" : "sync_config_required", message: "Confirm synchronization for the current camera inputs." };
  return null;
}

export function legacySyncFixture(taskId: string) {
  const versions = { cam_01: "cam_01-0", cam_02: "cam_02-0", cam_03: "cam_03-0", cam_04: "cam_04-0" };
  const uploads = new Map<string, number>();
  let config: SyncConfig | null = null;
  const times = [0, 40, 80, 120, 160, 200, 240, 280, 320, 360];
  const status = (): SyncStatus => !config ? "unconfirmed" : cameras.every(camera => config!.input_versions[camera] === versions[camera]) ? "confirmed" : "stale";
  const publicSync = () => ({ status: status(), source_versions: { ...versions }, config });
  const error = (code: string, message: string, httpStatus = 422) => Response.json({ detail: { code, message } }, { status: httpStatus });
  const base = `/api/v1/tasks/${taskId}/sync`;
  return {
    get status() { return status(); },
    replaceInput(slot: string) {
      if (!cameras.includes(slot as typeof cameras[number])) return;
      const camera = slot as typeof cameras[number], revision = (uploads.get(camera) || 0) + 1;
      uploads.set(camera, revision); versions[camera] = `${camera}-${revision}`;
    },
    response(url: URL, method = "GET", body?: unknown): Response | undefined {
      if (!url.pathname.startsWith(base)) return undefined;
      if (url.pathname === base && method === "GET") return Response.json(publicSync());
      if (uploads.size !== 4) return error("input_missing", "Upload all four cameras first.");
      if (url.pathname === `${base}/preview`) return Response.json({
        status: "ready", source_versions: { ...versions }, error: null,
        cameras: Object.fromEntries(cameras.map(camera => [camera, { source_version: versions[camera], duration_ms: 400, fps: 25, frame_count: 10, source_start_pts_ms: 0, frame_timestamps_ms: times, video_url: `${base}/preview/${camera}?source_version=${versions[camera]}` }])),
      }, { status: method === "POST" ? 202 : 200 });
      const camera = url.pathname.split("/").at(-1) as typeof cameras[number];
      if (url.pathname.includes("/preview/") || url.pathname.includes("/frames/")) {
        if (!cameras.includes(camera) || url.searchParams.get("source_version") !== versions[camera]) return error("sync_stale", "Camera source version changed.", 409);
        if (url.pathname.includes("/preview/")) return new Response(legacyPreviewVideo, { headers: { "Content-Type": "video/mp4" } });
        const requested = Number(url.searchParams.get("time_ms"));
        if (!Number.isFinite(requested) || requested < 0 || requested >= 400) return error("sync_invalid", "Frame time is outside the video.");
        const actual = times.reduce((previous, next) => Math.abs(requested - next) < Math.abs(requested - previous) ? next : previous);
        return Response.json({ camera, source_version: versions[camera], requested_time_ms: requested, actual_time_ms: actual, source_pts_ms: actual, frame_index: times.indexOf(actual), image_data_url: legacyFrameImage });
      }
      if (url.pathname === base && method === "PUT") {
        const candidate = body as { input_versions?: CameraValues<string>; selected_timestamps_ms?: CameraValues<number> } | undefined;
        if (!candidate?.input_versions || cameras.some(camera => candidate.input_versions![camera] !== versions[camera])) return error("sync_stale", "All current camera versions are required.", 409);
        const selected = candidate.selected_timestamps_ms;
        if (!selected || Object.keys(selected).length !== 4 || cameras.some(camera => !Number.isFinite(selected[camera]) || !times.includes(selected[camera]))) return error("sync_invalid", "Select a measured frame for each camera.");
        const offsets = Object.fromEntries(cameras.map(camera => [camera, selected[camera] - selected.cam_03])) as CameraValues<number>;
        const start = Math.max(...cameras.map(camera => -offsets[camera])), end = Math.min(...cameras.map(camera => 400 - offsets[camera]));
        if (start >= end) return error("sync_no_overlap", "No common overlap.");
        config = { schema_version: 1, anchor_camera: "cam_03", camera_time_offsets_ms: offsets, selected_timestamps_ms: { ...selected }, input_versions: { ...versions }, durations_ms: { cam_01: 400, cam_02: 400, cam_03: 400, cam_04: 400 }, overlap_start_ms: start, overlap_end_ms: end, confirmed_at: "2026-09-07T01:00:00Z" };
        return Response.json(publicSync());
      }
      return error("task_state_conflict", "Unsupported fixture request.", 409);
    },
  };
}
