import { Icon, type IconName } from "./Icon";
import type { TaskStatus } from "../workspace/types";
import { useLocale } from "../providers/LocaleProvider";
import { taskStatusLabel } from "../workspace/labels";

const statusIcons = {
  draft: "pencil", uploading: "upload", queued: "clock", running: "activity",
  canceling: "stop", completed: "statusCheck", failed: "alert", canceled: "ban", expired: "calendarX",
} as const satisfies Record<TaskStatus | "canceling", IconName>;

export function StatusChip({ status, stageMessage, compact = false, id }: {
  id?: string;
  status: TaskStatus;
  stageMessage?: string;
  compact?: boolean;
}) {
  const { locale } = useLocale();
  // The public API groups cancel_requested under running, retaining its stage message
  const displayStatus = status === "running" && ["正在取消", "Canceling"].includes(stageMessage?.trim() ?? "") ? "canceling" : status;
  const label = displayStatus === "canceling" ? (locale === "zh" ? "正在取消" : "Canceling") : taskStatusLabel(locale, status);
  return <span id={id} className={`status-chip status-${displayStatus}${compact ? " status-chip-compact" : ""}`} title={compact ? label : undefined}>
    <span className="status-symbol" aria-hidden="true"><Icon name={statusIcons[displayStatus]} size={14}/></span>
    <span className={compact ? "sr-only" : "status-label"}>{label}</span>
  </span>;
}
