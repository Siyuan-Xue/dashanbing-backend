import type { components } from "../generated/schema";
import { ApiError } from "../api";
import { notifySessionExpired } from "../session";

export type ApiKey = components["schemas"]["ApiKeyPublic"];
export type CreatedApiKey = components["schemas"]["ApiKeyCreated"];
export type ApiKeyCreate = components["schemas"]["ApiKeyCreate"];
export type AccountUsage = components["schemas"]["AccountUsage"];

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
  createKey: (payload: ApiKeyCreate) => request<CreatedApiKey>("/api/v1/api-keys", {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload),
  }),
  revokeKey: (id: string) => request<void>(`/api/v1/api-keys/${encodeURIComponent(id)}`, { method: "DELETE" }),
};
