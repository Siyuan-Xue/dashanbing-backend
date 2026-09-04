import type { AccountUsage, Preset, ProductResult, Task, TaskMode, TaskPage, TaskSlot } from "./types";

export class WorkspaceApiError extends Error {
  constructor(public readonly status: number, message: string) {
    super(message);
    this.name = "WorkspaceApiError";
  }
}
async function messageFromResponse(response: Response) {
  try {
    const value = await response.json() as { detail?: unknown };
    if (typeof value.detail === "string") return value.detail;
  } catch {
    // Preserve a stable fallback for HTML/proxy failures.
  }
  return "Request failed";
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, { credentials: "include", ...init });
  if (!response.ok) throw new WorkspaceApiError(response.status, await messageFromResponse(response));
  if (response.status === 204) return undefined as T;
  return response.json() as Promise<T>;
}

function jsonInit(method: string, body?: unknown): RequestInit {
  return {
    method,
    headers: body === undefined ? undefined : { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  };
}

export const workspaceApi = {
  createTask: (title: string, mode: TaskMode) => request<Task>("/api/v1/tasks", jsonInit("POST", { title, mode })),
  submitTask: (taskId: string) => request<Task>(`/api/v1/tasks/${taskId}/submit`, jsonInit("POST")),
  getTask: (taskId: string) => request<Task>(`/api/v1/tasks/${taskId}`),
  listTasks: (params: URLSearchParams) => request<TaskPage>(`/api/v1/tasks?${params}`),
  cancelTask: (taskId: string) => request<Task>(`/api/v1/tasks/${taskId}/cancel`, jsonInit("POST")),
  retryTask: (taskId: string) => request<Task>(`/api/v1/tasks/${taskId}/retry`, jsonInit("POST")),
  deleteTask: (taskId: string) => request<void>(`/api/v1/tasks/${taskId}`, jsonInit("DELETE")),
  taskResult: (taskId: string) => request<ProductResult>(`/api/v1/tasks/${taskId}/result`),
  presets: () => request<Preset[]>("/api/v1/presets"),
  presetResult: (presetId: string) => request<ProductResult>(`/api/v1/presets/${encodeURIComponent(presetId)}/result`),
  createFromPreset: (presetId: string, mode: TaskMode) => request<Task>("/api/v1/tasks/from-preset", jsonInit("POST", { preset_id: presetId, mode })),
  usage: () => request<AccountUsage>("/api/v1/account/usage"),
};

export function uploadTaskInput(taskId: string, slot: TaskSlot, file: File, onProgress: (progress: number) => void) {
  return new Promise<Task>((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open("PUT", `/api/v1/tasks/${taskId}/inputs/${slot}`);
    xhr.withCredentials = true;
    xhr.upload.addEventListener("progress", (event) => {
      if (event.lengthComputable && event.total > 0) onProgress(Math.round((event.loaded / event.total) * 100));
    });
    xhr.addEventListener("error", () => reject(new WorkspaceApiError(0, "Network error")));
    xhr.addEventListener("abort", () => reject(new WorkspaceApiError(0, "Upload canceled")));
    xhr.addEventListener("load", () => {
      let payload: unknown;
      try { payload = xhr.responseText ? JSON.parse(xhr.responseText) : undefined; } catch { payload = undefined; }
      if (xhr.status >= 200 && xhr.status < 300) {
        onProgress(100);
        resolve(payload as Task);
        return;
      }
      const detail = typeof payload === "object" && payload !== null && typeof (payload as { detail?: unknown }).detail === "string"
        ? (payload as { detail: string }).detail : "Upload failed";
      reject(new WorkspaceApiError(xhr.status, detail));
    });
    const form = new FormData();
    form.append("file", file, file.name);
    xhr.send(form);
  });
}
