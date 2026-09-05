import { jsonInit, request } from "../workspace/api";
import type { AnalystContext, ComparisonReportState, AnalystLocale, AnalystSource, AnalystStyle, ContextInput, Conversation, Observation, ProfileInput, ReportState, TrainingProfile } from "./types";
const encode = encodeURIComponent;
const root = "/api/v1";
export const analystPath = (source: AnalystSource) => `${root}/${source.kind === "task" ? "tasks" : "presets"}/${encode(source.id)}/analyst`;
export const analystApi = {
  profiles: (signal?: AbortSignal) => request<TrainingProfile[]>(`${root}/training-profiles`, { signal }).then(value => { if (!Array.isArray(value)) throw new Error("Invalid profiles response"); return value; }),
  createProfile: (body: ProfileInput) => request<TrainingProfile>(`${root}/training-profiles`, jsonInit("POST", body)),
  updateProfile: (id: string, body: Omit<ProfileInput, "kind">) => request<TrainingProfile>(`${root}/training-profiles/${encode(id)}`, jsonInit("PATCH", body)),
  deleteProfile: (id: string) => request<void>(`${root}/training-profiles/${encode(id)}`, jsonInit("DELETE")),
  history: (id: string, signal?: AbortSignal) => request<Observation[]>(`${root}/training-profiles/${encode(id)}/history`, { signal }),
  context: (source: AnalystSource, signal?: AbortSignal) => request<AnalystContext>(`${analystPath(source)}/context`, { signal }).then(value => { if (!value?.facts || !Array.isArray(value.subjects)) throw new Error("Invalid analyst context"); return value; }),
  updateContext: (source: AnalystSource, body: ContextInput, signal?: AbortSignal) => request<AnalystContext>(`${analystPath(source)}/context`, { ...jsonInit("PUT", body), signal }),
  report: async (source: AnalystSource, locale: AnalystLocale, style: AnalystStyle, signal?: AbortSignal) => {
    const value = await request<ReportState>(`${analystPath(source)}/report?${new URLSearchParams({ locale, style })}`, { signal });
    if (!value || !["disabled", "waiting", "queued", "running", "completed", "failed"].includes(value.status) || (value.status === "completed" && !value.report)) throw new Error("Invalid analyst response");
    return value;
  },
  generate: (source: AnalystSource, locale: AnalystLocale, style: AnalystStyle, regenerate: boolean, signal?: AbortSignal) => {
    if (source.kind === "preset") return Promise.reject(new Error("Preset reports are read only"));
    return request<ReportState>(`${analystPath(source)}/report`, { ...jsonInit("POST", { locale, style, regenerate }), signal });
  },
  comparisons: (source: AnalystSource, locale: AnalystLocale, style: AnalystStyle, signal?: AbortSignal) => request<{ items: ComparisonReportState[] }>(`${analystPath(source)}/comparisons?${new URLSearchParams({ locale, style })}`, { signal }).then(value => { if (!value || !Array.isArray(value.items)) throw new Error("Invalid comparison response"); return value.items; }),
  compare: (source: AnalystSource, comparison_id: string, locale: AnalystLocale, style: AnalystStyle, signal?: AbortSignal) => request<ComparisonReportState>(`${analystPath(source)}/comparisons`, { ...jsonInit("POST", { comparison_id, locale, style }), signal }),
  createConversation: (source: AnalystSource, scope: { subject_id?: string; comparison_id?: string; locale: AnalystLocale; style: AnalystStyle }, signal?: AbortSignal) => request<Conversation>(`${root}/analyst/conversations`, { ...jsonInit("POST", { [source.kind === "task" ? "task_id" : "preset_id"]: source.id, ...scope }), signal }),
  conversation: (id: string, signal?: AbortSignal) => request<Conversation>(`${root}/analyst/conversations/${encode(id)}`, { signal }),
  send: (id: string, content: string, requestId: string, signal?: AbortSignal) => request<{ message_id: string; job_id: string }>(`${root}/analyst/conversations/${encode(id)}/messages`, { ...jsonInit("POST", { content, request_id: requestId }), signal }),
  eventsUrl: (id: string) => `${root}/analyst/conversations/${encode(id)}/events`,
};
