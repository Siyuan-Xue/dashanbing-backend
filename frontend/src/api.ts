import createClient from "openapi-fetch";

import type { paths } from "./generated/schema";

// Generated contracts remain the source for staged-task APIs. Auth uses the
// current server contract directly until the planned Task 6 schema refresh.
export const api = createClient<paths>({ credentials: "include" });

export type AuthUser = {
  id: number;
  username: string;
  email: string | null;
  is_active: boolean;
};

export type Registration = {
  username: string;
  email: string;
  password: string;
};

export class ApiError extends Error {
  constructor(
    public readonly status: number,
    message: string,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

async function readError(response: Response) {
  try {
    const payload = (await response.json()) as { detail?: unknown };
    if (typeof payload.detail === "string") return payload.detail;
    if (Array.isArray(payload.detail)) {
      return payload.detail
        .map((item) => (typeof item === "object" && item && "msg" in item ? String(item.msg) : ""))
        .filter(Boolean)
        .join("; ");
    }
  } catch {
    // A non-JSON proxy error still receives a stable localized message in UI.
  }
  return "Request failed";
}

async function jsonRequest<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, { credentials: "include", ...init });
  if (!response.ok) throw new ApiError(response.status, await readError(response));
  return response.json() as Promise<T>;
}

export const authApi = {
  me: () => jsonRequest<AuthUser>("/api/v1/users/me"),
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
    if (!response.ok) throw new ApiError(response.status, await readError(response));
  },
};
