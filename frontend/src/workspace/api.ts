import type { AccountUsage, Preset, ProductResult, Task, TaskMode, TaskPage, TaskSlot } from "./types";
import { ApiError } from "../api";
import type { ApiValidationIssue } from "../api";
import { notifySessionExpired } from "../session";

export class WorkspaceApiError extends ApiError {
  constructor(status: number, message: string, validationIssues: ApiValidationIssue[] = []) {
    super(status, message, validationIssues);
    this.name = "WorkspaceApiError";
  }
}

function errorFromPayload(payload: unknown, fallback = "Request failed") {
  if (typeof payload !== "object" || payload === null) return { message: fallback, validationIssues: [] as ApiValidationIssue[] };
  const detail = (payload as { detail?: unknown }).detail;
  if (typeof detail === "string") return { message: detail, validationIssues: [] as ApiValidationIssue[] };
  if (Array.isArray(detail)) {
    const issues = detail.flatMap((item): ApiValidationIssue[] => {
      if (typeof item !== "object" || item === null) return [];
      const issue = item as { loc?: unknown; type?: unknown };
      const field = Array.isArray(issue.loc) ? issue.loc.at(-1) : undefined;
      return typeof field === "string" && typeof issue.type === "string" ? [{ field, type: issue.type }] : [];
    });
    if (issues.length) return { message: fallback, validationIssues: issues };
  }
  return { message: fallback, validationIssues: [] as ApiValidationIssue[] };
}

async function responseError(response: Response) {
  try { return errorFromPayload(await response.json()); }
  catch { return errorFromPayload(undefined); }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, { credentials: "include", ...init });
  if (!response.ok) {
    if (response.status === 401) notifySessionExpired();
    const error = await responseError(response);
    throw new WorkspaceApiError(response.status, error.message, error.validationIssues);
  }
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
  getTask: (taskId: string, signal?: AbortSignal) => request<Task>(`/api/v1/tasks/${taskId}`, { signal }),
  listTasks: (params: URLSearchParams) => request<TaskPage>(`/api/v1/tasks?${params}`),
  cancelTask: (taskId: string) => request<Task>(`/api/v1/tasks/${taskId}/cancel`, jsonInit("POST")),
  retryTask: (taskId: string) => request<Task>(`/api/v1/tasks/${taskId}/retry`, jsonInit("POST")),
  deleteTask: (taskId: string) => request<void>(`/api/v1/tasks/${taskId}`, jsonInit("DELETE")),
  taskResult: (taskId: string, signal?: AbortSignal) => request<ProductResult>(`/api/v1/tasks/${taskId}/result`, { signal }),
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
      if (xhr.status === 401) notifySessionExpired();
      const error = errorFromPayload(payload, "Upload failed");
      reject(new WorkspaceApiError(xhr.status, error.message, error.validationIssues));
    });
    const form = new FormData();
    form.append("file", file, file.name);
    xhr.send(form);
  });
}
