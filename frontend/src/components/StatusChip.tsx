import { Icon } from "./Icon";
import type { TaskStatus } from "../workspace/types";
import { useLocale } from "../providers/LocaleProvider";
import { taskStatusLabel } from "../workspace/labels";

export function StatusChip({ status }: { status: TaskStatus }) {
  const { locale } = useLocale();
  return <span className={`status-chip status-${status}`}><i aria-hidden="true"><Icon name={status === "completed" ? "check" : ["failed", "expired", "canceled"].includes(status) ? "x" : "clock"} size={12}/></i>{taskStatusLabel(locale, status)}</span>;
}
