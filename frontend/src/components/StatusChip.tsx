import type { TaskStatus } from "../workspace/types";
import { useLocale } from "../providers/LocaleProvider";
import { taskStatusLabel } from "../workspace/labels";

export function StatusChip({ status }: { status: TaskStatus }) {
  const { locale } = useLocale();
  return <span className={`status-chip status-${status}`}><i/>{taskStatusLabel(locale, status)}</span>;
}
