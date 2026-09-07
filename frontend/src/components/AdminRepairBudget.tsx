import type { RepairBudget } from "../lib/adminApi";
import { useAdminCopy } from "../lib/adminCopy";
export function AdminRepairBudget({ value }: { value: RepairBudget }) { const t = useAdminCopy(); return <section className="admin-budget"><h2>{t("repairBudget")}</h2><div><time>{value.utc_date}</time><span>{t("video")} {value.video_used} / {value.video_limit}</span><span>{t("ai")} {value.ai_used} / {value.ai_limit}</span></div><p>{t("repairHelp")}</p></section>; }
