import type { TaskStatus } from "../workspace/types";

const labels = {
  zh: { draft: "草稿", uploading: "上传中", queued: "排队中", running: "分析中", completed: "已完成", failed: "失败", canceled: "已取消", expired: "已过期" },
  en: { draft: "Draft", uploading: "Uploading", queued: "Queued", running: "Running", completed: "Completed", failed: "Failed", canceled: "Canceled", expired: "Expired" },
};

export function StatusChip({ status }: { status: TaskStatus }) {
  const locale = document.documentElement.lang.startsWith("en") ? "en" : "zh";
  return <span className={`status-chip status-${status}`}><i/>{labels[locale][status]}</span>;
}
