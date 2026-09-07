import type { components } from "../generated/schema";
import { ApiError } from "../api";
import { notifySessionExpired } from "../session";

export type ApiKey = components["schemas"]["ApiKeyPublic"];
export type CreatedApiKey = components["schemas"]["ApiKeyCreated"];
export type ApiKeyCreate = components["schemas"]["ApiKeyCreate"];
export type AccountUsage = components["schemas"]["AccountUsage"];
export type AccountLimits = {
  quotas: { drafts: number; unfinished: number; daily_video: number; daily_ai: number };
  application: { max_upload_size_gb: number; draft_ttl_hours: number; enrollment_retention_days: number; raw_retention_days: number; result_retention_days: number; analyst_daily_limit: number };
};

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, { credentials: "include", ...init });
  if (!response.ok) {
    if (response.status === 401) notifySessionExpired();
    let message = "Request failed";
    try {
      const body = await response.json() as { detail?: unknown };
      if (typeof body.detail === "string") message = body.detail;
    } catch { /* stable fallback */ }
    throw new ApiError(response.status, message);
  }
  if (response.status === 204) return undefined as T;
  return response.json() as Promise<T>;
}

export const apiCenterApi = {
  keys: () => request<ApiKey[]>("/api/v1/api-keys"),
  usage: () => request<AccountUsage>("/api/v1/account/usage"),
  limits: () => request<AccountLimits>("/api/v1/account/limits"),
  createKey: (payload: ApiKeyCreate) => request<CreatedApiKey>("/api/v1/api-keys", {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload),
  }),
  revokeKey: (id: string) => request<void>(`/api/v1/api-keys/${encodeURIComponent(id)}`, { method: "DELETE" }),
};
