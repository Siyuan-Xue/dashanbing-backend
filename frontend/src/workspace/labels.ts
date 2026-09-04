import type { Locale } from "../copy";
import type { Preset, ProductEvent, TaskMode, TaskStatus } from "./types";

const statusLabels: Record<Locale, Record<TaskStatus, string>> = {
  zh: { draft: "草稿", uploading: "上传中", queued: "排队中", running: "分析中", completed: "已完成", failed: "失败", canceled: "已取消", expired: "已过期" },
  en: { draft: "Draft", uploading: "Uploading", queued: "Queued", running: "Running", completed: "Completed", failed: "Failed", canceled: "Canceled", expired: "Expired" },
};

const modeLabels: Record<Locale, Record<TaskMode, string>> = {
  zh: { quick: "快速", full: "完整" },
  en: { quick: "Quick", full: "Full" },
};

const sourceLabels: Record<Locale, Record<string, string>> = {
  zh: { upload: "上传", preset: "示例" },
  en: { upload: "Upload", preset: "Preset" },
};

const actionLabels: Record<Locale, Record<ProductEvent["action_type"], string>> = {
  zh: { triple_threat: "三威胁", free_throw: "罚球", jump_shot: "跳投", layup: "上篮" },
  en: { triple_threat: "Triple threat", free_throw: "Free throw", jump_shot: "Jump shot", layup: "Layup" },
};

const outcomeLabels: Record<Locale, Record<NonNullable<ProductEvent["result"]>, string>> = {
  zh: { make: "命中", miss: "未中", undetermined: "待确认" },
  en: { make: "Made", miss: "Missed", undetermined: "Undetermined" },
};

const presetLabels: Record<string, Record<Locale, { title: string; description: string; tag: string }>> = {
  "quick-demo": { zh: { title: "快速演示", description: "4 次跳投", tag: "快速" }, en: { title: "Quick demo", description: "4 jump shots", tag: "Quick" } },
  "mixed-actions": { zh: { title: "混合动作", description: "三威胁与跳投", tag: "完整" }, en: { title: "Mixed actions", description: "Triple threat and jump shots", tag: "Full" } },
  "verified-outcome": { zh: { title: "命中验证", description: "带投篮结果真值的罚篮样例", tag: "已验证" }, en: { title: "Verified outcomes", description: "Free throws with verified shot outcomes", tag: "Verified" } },
  "layup-demo": { zh: { title: "上篮演示", description: "6 次上篮", tag: "上篮" }, en: { title: "Layup demo", description: "6 layups", tag: "Layup" } },
};

export const taskStatusLabel = (locale: Locale, status: TaskStatus) => statusLabels[locale][status];
export const taskModeLabel = (locale: Locale, mode: TaskMode) => modeLabels[locale][mode];
export const taskSourceLabel = (locale: Locale, source: string) => sourceLabels[locale][source] || source;
export const actionLabel = (locale: Locale, action: ProductEvent["action_type"]) => actionLabels[locale][action];
export const outcomeLabel = (locale: Locale, outcome: ProductEvent["result"]) => outcome ? outcomeLabels[locale][outcome] : "—";
export const localizePreset = (locale: Locale, preset: Preset) => presetLabels[preset.id]?.[locale] || { title: preset.title, description: preset.description, tag: "" };
