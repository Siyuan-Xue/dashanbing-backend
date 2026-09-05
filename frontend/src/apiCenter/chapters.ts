import type { Locale } from "../copy";

type Heading = { id: string; title: Record<Locale, string> };
type Chapter = Heading & { children: readonly Heading[] };

// Stable IDs are shared by article headings, deep links, and both translations of the TOC.
export const apiChapters = [
  { id: "overview", title: { zh: "模式比较", en: "Mode comparison" }, children: [] },
  { id: "auth", title: { zh: "认证", en: "Authentication" }, children: [] },
  { id: "workflow", title: { zh: "创建与上传", en: "Create and upload" }, children: [
    { id: "create", title: { zh: "创建草稿", en: "Create a draft" } },
    { id: "upload", title: { zh: "上传输入", en: "Upload inputs" } },
    { id: "submit", title: { zh: "提交任务", en: "Submit a task" } },
  ] },
  { id: "polling", title: { zh: "轮询与结果", en: "Polling and results" }, children: [
    { id: "poll-status", title: { zh: "轮询任务状态", en: "Poll task status" } },
    { id: "result", title: { zh: "获取结果", en: "Get results" } },
    { id: "media", title: { zh: "复核媒体", en: "Review media" } },
  ] },
  { id: "lifecycle", title: { zh: "任务生命周期", en: "Task lifecycle" }, children: [] },
  { id: "limits", title: { zh: "配额、文件限制与保留", en: "Quotas, file limits, and retention" }, children: [] },
  { id: "examples", title: { zh: "可执行示例", en: "Executable examples" }, children: [
    { id: "curl", title: { zh: "Curl", en: "Curl" } },
    { id: "python", title: { zh: "Python", en: "Python" } },
  ] },
  { id: "errors", title: { zh: "状态与常见错误", en: "Statuses and common errors" }, children: [] },
] as const satisfies readonly Chapter[];

export type ApiHeadingId = typeof apiChapters[number]["id"] | typeof apiChapters[number]["children"][number]["id"];
export const apiHeadings = apiChapters.flatMap(chapter => [
  { id: chapter.id, title: chapter.title, level: 2 as const },
  ...chapter.children.map(child => ({ ...child, level: 3 as const })),
]);

export function headingFromHash(hash: string) {
  try {
    const id = decodeURIComponent(hash.replace(/^#/, ""));
    return apiHeadings.find(heading => heading.id === id);
  } catch {
    return undefined;
  }
}
