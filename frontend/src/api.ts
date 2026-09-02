import createClient from "openapi-fetch";

import type { components, paths } from "./generated/schema";

export const api = createClient<paths>({ credentials: "include" });

export type Analysis = components["schemas"]["AnalysisPublic"];
export type ProductResult = components["schemas"]["ProductResult"];

export type Preset = components["schemas"]["PresetPublic"];

export type Readiness = {
  ready: boolean;
  mode: "gpu" | "simulation";
  checks: Array<{ name: string; ready: boolean; detail: string }>;
};

export function errorMessage(error: unknown, fallback = "请求失败") {
  if (typeof error === "object" && error && "detail" in error) {
    const detail = (error as { detail?: unknown }).detail;
    if (typeof detail === "string") return detail;
  }
  return fallback;
}

export async function uploadAnalysis(form: FormData): Promise<Analysis> {
  const response = await fetch("/api/v1/analyses/upload", {
    method: "POST",
    credentials: "include",
    body: form,
  });
  if (!response.ok) throw await response.json();
  return response.json();
}
