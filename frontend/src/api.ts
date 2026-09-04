import createClient from "openapi-fetch";

import type { components, paths } from "./generated/schema";

// Generated contracts are the source for both staged-task and auth APIs.
export const api = createClient<paths>({ credentials: "include" });

export type AuthUser = components["schemas"]["UserPublic"];
export type Registration = components["schemas"]["UserRegistration"];

export type ApiValidationIssue = {
  field: string;
  type: string;
};

export class ApiError extends Error {
  constructor(
    public readonly status: number,
    message: string,
    public readonly validationIssues: ApiValidationIssue[] = [],
  ) {
    super(message);
    this.name = "ApiError";
  }
}

async function readError(response: Response): Promise<{ message: string; validationIssues: ApiValidationIssue[] }> {
  try {
    const payload = (await response.json()) as { detail?: unknown };
    if (typeof payload.detail === "string") return { message: payload.detail, validationIssues: [] };
    if (Array.isArray(payload.detail)) {
      const details = payload.detail.filter((item): item is { msg?: unknown; loc?: unknown; type?: unknown } => typeof item === "object" && item !== null);
      const message = details.map((item) => typeof item.msg === "string" ? item.msg : "").filter(Boolean).join("; ");
      const validationIssues = details.flatMap((item) => {
        const field = Array.isArray(item.loc) ? item.loc.at(-1) : undefined;
        return typeof field === "string" && typeof item.type === "string" ? [{ field, type: item.type }] : [];
      });
      if (message || validationIssues.length) return { message: message || "Validation failed", validationIssues };
    }
  } catch {
    // A non-JSON proxy error still receives a stable localized message in UI.
  }
  return { message: "Request failed", validationIssues: [] };
}

async function jsonRequest<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, { credentials: "include", ...init });
  if (!response.ok) {
    const error = await readError(response);
    throw new ApiError(response.status, error.message, error.validationIssues);
  }
  return response.json() as Promise<T>;
}

function isAuthUser(value: unknown): value is AuthUser {
  if (typeof value !== "object" || value === null) return false;
  const user = value as Record<string, unknown>;
  return typeof user.id === "number"
    && typeof user.username === "string"
    && (typeof user.email === "string" || user.email === null)
    && typeof user.is_active === "boolean";
}

export const authApi = {
  me: async () => {
    const user = await jsonRequest<unknown>("/api/v1/users/me");
    if (!isAuthUser(user)) throw new ApiError(0, "Invalid user response");
    return user;
  },
  register: (registration: Registration) =>
    jsonRequest<AuthUser>("/api/v1/register", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(registration),
    }),
  login: (identity: string, password: string) => {
    const body = new URLSearchParams();
    body.set("username", identity);
    body.set("password", password);
    return jsonRequest<{ access_token: string; token_type: string }>("/api/v1/login/access-token", {
      method: "POST",
      headers: { "Content-Type": "application/x-www-form-urlencoded" },
      body,
    });
  },
  logout: async () => {
    const response = await fetch("/api/v1/logout", {
      method: "POST",
      credentials: "include",
    });
    if (!response.ok) {
      const error = await readError(response);
      throw new ApiError(response.status, error.message, error.validationIssues);
    }
  },
};
