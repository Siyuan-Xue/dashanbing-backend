import { ApiError } from "../api";
import { notifySessionExpired } from "../session";
import type { AdminCopyKey } from "./adminCopy";

export type QuotaKey = "drafts" | "unfinished" | "daily_video" | "daily_ai";
export const quotaKeys: QuotaKey[] = ["drafts", "unfinished", "daily_video", "daily_ai"];
export type Quotas = Record<QuotaKey, number>;
export type Bounds = { min: number; max: number };
export type Page<T> = { items: T[]; total: number; page: number; page_size: number };
export type AdminUser = { id: number; username: string; email: string | null; role: "user"; is_active: boolean; created_at: string; quotas: Quotas; quota_overrides: Partial<Quotas>; usage: Quotas };
export type RepairBudget = { utc_date: string; video_used: number; video_limit: number; ai_used: number; ai_limit: number };
export type SettingsValues = { video_enabled: boolean; video_paused: boolean; ai_enabled: boolean; ai_paused: boolean; ai_concurrency: number; default_quotas: Quotas };
export type AdminSettings = { current: SettingsValues; bounds: { ai_concurrency: Bounds; priority: Bounds; quotas: Record<QuotaKey, Bounds>; batch_size: number; admin_retries: number }; repair_budget: RepairBudget };
export type SettingsPatch = Partial<Omit<SettingsValues, "default_quotas">> & { default_quotas?: Partial<Quotas> };
export type JobKind = "video" | "ai" | "preset";
export type JobAction = "hold" | "release" | "priority" | "retry" | "backfill";
export type AdminJob = { id: string; kind: JobKind; owner_id: number | null; task_id: string | null; status: string; created_at: string; updated_at: string; attempts: number; held: boolean; priority: number; admin_retries: number; allowed_actions: JobAction[] };
export type AdminAudit = { id: string; actor_id: number; action: string; target_kind: string; target_ids: (string | number)[]; reason: string; changes: Record<string, unknown>; created_at: string };
export type QueueCounts = { queued: number; running: number; failed: number; completed: number };
export type AdminTimingSummary = { count: number; p50: number | null; p95: number | null };
export type AdminTimingKey = "video_queue_seconds" | "video_execution_seconds" | "ai_total_seconds";
export type AdminOverview = {
  timings?: Record<AdminTimingKey, AdminTimingSummary>;
  errors?: { kind: JobKind; code: string; count: number }[];
  resources: { cpu: { logical_count: number | null; load_average: number[] | null; utilization_percent?: number }; memory: { total_bytes: number; available_bytes: number } | null; disk: { total_bytes: number; used_bytes: number; free_bytes: number } | null; gpu: { utilization_percent: number; memory_used_bytes: number; memory_total_bytes: number }[] | null };
  queues: Record<JobKind, QueueCounts>; usage: { ai_attempts: number; ai_tokens: number; video_submissions: number }; users: { total: number; active: number }; repair_budget: RepairBudget;
};
export type AdminDeployment = { application: { version: string; database_revision: string | null }; workers: { video_enabled: boolean; ai_enabled: boolean }; backup: { status: string }; read_only: true };
export type JobActionPayload = { kind: JobKind; ids: string[]; action: JobAction; priority?: number };

export function adminErrorKey(error: unknown): AdminCopyKey {
  if (error instanceof ApiError) {
    if (error.status === 401 || error.status === 403) return "forbidden";
    if (error.status === 409) return "conflict";
    if (error.status === 429) return "budgetExhausted";
    if (error.status === 422) return "invalidValues";
    if (error.status >= 500) return "unavailable";
  }
  return "requestFailed";
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`/api/v1/admin${path}`, { credentials: "include", cache: "no-store", ...init });
  if (!response.ok) {
    if (response.status === 401) notifySessionExpired();
    // Error bodies can contain service details; only status controls visible copy.
    throw new ApiError(response.status, "Administrator request failed");
  }
  if (response.status === 204) return undefined as T;
  return response.json() as Promise<T>;
}
function query(params: Record<string, string | number | undefined>) { const result = new URLSearchParams(); for (const [key, value] of Object.entries(params)) if (value !== undefined && value !== "") result.set(key, String(value)); return `?${result}`; }
function mutate<T>(path: string, method: string, values: object, reason: string) {
  const trimmed = reason.trim();
  if (trimmed.length < 3 || trimmed.length > 500) return Promise.reject(new ApiError(422, "Invalid reason"));
  return request<T>(path, { method, headers: { "Content-Type": "application/json" }, body: JSON.stringify({ ...values, reason: trimmed }) });
}
export const adminApi = {
  overview: () => request<AdminOverview>("/overview"),
  deployment: () => request<AdminDeployment>("/deployment"),
  settings: () => request<AdminSettings>("/settings"),
  users: (params: { page: number; page_size: number; q?: string; is_active?: string }) => request<Page<AdminUser>>(`/users${query(params)}`),
  jobs: (params: { page: number; page_size: number; kind?: string; status?: string }) => request<Page<AdminJob>>(`/jobs${query(params)}`),
  audit: (params: { page: number; page_size: number }) => request<Page<AdminAudit>>(`/audit${query(params)}`),
  updateUser: (id: number, values: { is_active?: boolean; quotas?: Partial<Record<QuotaKey, number | null>> }, reason: string) => mutate<AdminUser>(`/users/${id}`, "PATCH", values, reason),
  revokeSessions: (id: number, reason: string) => mutate<void>(`/users/${id}/force-logout`, "POST", {}, reason),
  updateSettings: (values: SettingsPatch, reason: string) => mutate<AdminSettings>("/settings", "PATCH", values, reason),
  act: (values: JobActionPayload, reason: string) => {
    if (!values.ids.length || values.ids.length > 10 || new Set(values.ids).size !== values.ids.length) return Promise.reject(new ApiError(422, "Invalid selection"));
    return mutate<{ items: { id: string; status: string }[] }>("/jobs/actions", "POST", values, reason);
  },
};
