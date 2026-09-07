import type { AdminOverview } from "../lib/adminApi";
import { useAdminCopy } from "../lib/adminCopy";
import { useAdminFormat } from "./AdminShared";
export function AdminResources({ value }: { value: AdminOverview["resources"] }) {
  const t = useAdminCopy(); const format = useAdminFormat();
  const fields: [string, string][] = [[t("cpuCores"), format.number(value.cpu.logical_count)], [t("cpuUsage"), value.cpu.utilization_percent == null ? t("unknown") : `${format.number(value.cpu.utilization_percent)}%`], [t("cpuLoad"), value.cpu.load_average?.map(format.number).join(" / ") || t("unknown")], [t("memory"), value.memory ? `${format.bytes(value.memory.available_bytes)} / ${format.bytes(value.memory.total_bytes)}` : t("unknown")], [t("disk"), value.disk ? `${format.bytes(value.disk.free_bytes)} / ${format.bytes(value.disk.total_bytes)}` : t("unknown")]];
  if (!value.gpu?.length) fields.push([t("gpu"), t("unknown")]); else value.gpu.forEach((gpu, index) => { fields.push([`${t("gpu")} ${index + 1}`, `${format.number(gpu.utilization_percent)}%`], [`${t("gpuMemory")} ${index + 1}`, `${format.bytes(gpu.memory_used_bytes)} / ${format.bytes(gpu.memory_total_bytes)}`]); });
  return <section className="admin-resources"><h2>{t("resourceUsage")}</h2><dl className="admin-metrics">{fields.map(([label, value]) => <div key={label}><dt>{label}</dt><dd>{value}</dd></div>)}</dl></section>;
}
