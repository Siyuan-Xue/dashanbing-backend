import { vi } from "vitest";
import type { Task, TaskSlot } from "../workspace/types";

export const cameras = ["cam_01", "cam_02", "cam_03", "cam_04"] as const;
export const versions = { cam_01: "v1", cam_02: "v2", cam_03: "v3", cam_04: "v4" };
export const selectedTimes = { cam_01: 120, cam_02: 80, cam_03: 40, cam_04: 160 };
export const config = {
  schema_version: 1, anchor_camera: "cam_03", camera_time_offsets_ms: { cam_01: 80, cam_02: 40, cam_03: 0, cam_04: 120 },
  selected_timestamps_ms: selectedTimes, input_versions: versions,
  durations_ms: { cam_01: 400, cam_02: 400, cam_03: 400, cam_04: 400 },
  overlap_start_ms: 0, overlap_end_ms: 280, confirmed_at: "2026-09-07T01:00:00Z",
};
export const preview = {
  status: "ready", source_versions: versions, error: null,
  cameras: Object.fromEntries(cameras.map(camera => [camera, {
    source_version: versions[camera], duration_ms: 400, fps: 25, frame_count: 10, source_start_pts_ms: 900,
    frame_timestamps_ms: [0, 40, 80, 120, 160, 200, 240, 280, 320, 360],
    video_url: `/api/v1/tasks/draft-1/sync/preview/${camera}?source_version=${versions[camera]}`,
  }])),
};
const input = (slot: TaskSlot, original_filename = `${slot}.mp4`) => ({ slot, original_filename, byte_size: 100, validation_state: "valid", created_at: "2026-09-07T01:00:00Z", updated_at: "2026-09-07T01:00:00Z" });
export function draftTask(overrides = {}) {
  return {
    id: "draft-1", title: "训练草稿", mode: "quick", analyst_locale: "zh", source_type: "upload", preset_id: null, status: "draft", progress: 0,
    stage_message: "Draft", error_code: null, error_message: null, submitted_at: null, created_via: "tasks_api", retry_count: 0,
    created_at: "2026-09-07T01:00:00Z", updated_at: "2026-09-07T01:00:00Z", started_at: null, completed_at: null,
    enrollment_mode: "sequential", expected_persons: null, sync_status: "unconfirmed",
    inputs: [input("enrollment_video"), ...cameras.map(camera => input(camera))], ...overrides,
  } as Task & { enrollment_mode: "sequential" | "lineup"; expected_persons: number | null; sync_status: string };
}

// Only network and browser media decoding are doubled; page, API, state and controls stay real.
export function installSyncServer(initial = draftTask()) {
  let task = initial;
  let sync = { status: initial.sync_status, source_versions: versions, config: initial.sync_status === "confirmed" ? config : null };
  const writes: Array<{ path: string; method: string; body: any }> = [];
  const frames: Array<{ camera: string; time: number; version: string | null }> = [];
  let previewState = structuredClone(preview);
  let confirmError: { code: string; message: string } | null = null;
  vi.stubGlobal("fetch", vi.fn(async (path: RequestInfo | URL, init?: RequestInit) => {
    const url = new URL(String(path), "http://localhost");
    const method = init?.method || "GET";
    const body = init?.body ? JSON.parse(String(init.body)) : undefined;
    if (method !== "GET") writes.push({ path: url.pathname, method, body });
    if (url.pathname === "/api/v1/presets") return Response.json([]);
    if (url.pathname === "/api/v1/tasks" && method === "POST") { task = { ...task, ...body }; return Response.json(task, { status: 201 }); }
    if (url.pathname === "/api/v1/tasks/draft-1") {
      if (method === "PATCH") task = { ...task, ...body };
      return Response.json(task);
    }
    if (url.pathname.endsWith("/return-to-input")) { task = { ...task, status: "draft", error_code: null }; return Response.json(task); }
    if (url.pathname.endsWith("/submit")) { task = { ...task, status: "queued" }; return Response.json(task); }
    if (url.pathname.endsWith("/sync/preview")) return Response.json(previewState, { status: method === "POST" ? 202 : 200 });
    if (url.pathname.includes("/sync/frames/")) {
      const camera = url.pathname.split("/").at(-1)!;
      const time = Number(url.searchParams.get("time_ms"));
      frames.push({ camera, time, version: url.searchParams.get("source_version") });
      const times = preview.cameras[camera].frame_timestamps_ms;
      const actual = times.reduce((best, value) => Math.abs(value - time) < Math.abs(best - time) ? value : best);
      return Response.json({ camera, source_version: preview.cameras[camera].source_version, requested_time_ms: time, actual_time_ms: actual, source_pts_ms: 900 + actual, frame_index: times.indexOf(actual), image_data_url: "data:image/jpeg;base64,/9j/2Q==" });
    }
    if (url.pathname.endsWith("/sync")) {
      if (method === "PUT") {
        if (confirmError) {
          if (confirmError.code === "sync_stale") task = { ...task, sync_status: "stale" };
          return Response.json({ detail: confirmError }, { status: 409 });
        }
        sync = { ...sync, status: "confirmed", config: { ...config, selected_timestamps_ms: body.selected_timestamps_ms } };
        task = { ...task, sync_status: "confirmed" };
      }
      return Response.json(sync);
    }
    return Response.json({ detail: "Not found" }, { status: 404 });
  }));
  vi.stubGlobal("XMLHttpRequest", class {
    url = ""; status = 0; responseText = ""; upload = { addEventListener() {} }; listeners = new Map<string, () => void>();
    open(_method: string, url: string) { this.url = url; }
    addEventListener(name: string, callback: () => void) { this.listeners.set(name, callback); }
    send(body: FormData) {
      const slot = this.url.split("/").at(-1) as TaskSlot;
      const file = body.get("file") as File;
      task = { ...task, inputs: [...task.inputs.filter(item => item.slot !== slot), input(slot, file.name)], sync_status: slot === "enrollment_video" ? task.sync_status : "stale" };
      this.status = 200; this.responseText = JSON.stringify(task); queueMicrotask(() => this.listeners.get("load")?.());
    }
  });
  return { get task() { return task; }, writes, frames,
    setPreview(value: typeof previewState) { previewState = value; },
    rejectConfirmation(value: typeof confirmError) { confirmError = value; },
  };
}
