import { useState } from "react";
import { adminApi, quotaKeys, type AdminAudit } from "../lib/adminApi";
import { useAdminCopy, type AdminCopyKey } from "../lib/adminCopy";
import { useAdminLoadable } from "../lib/adminLoadable";
import { AdminMetadataDrawer } from "../components/AdminMetadataDrawer";
import { AdminButton, AdminEmpty, AdminPager, AdminPanel, AdminTable, useAdminFormat, useAdminQuery } from "../components/AdminShared";
const actionLabels: Record<string, AdminCopyKey> = { "users.force_logout": "revoke", "users.update": "users", "settings.update": "save", "jobs.hold": "hold", "jobs.release": "release", "jobs.priority": "priority", "jobs.retry": "retryTask", "jobs.backfill": "backfill" };
const settingKeys = ["video_enabled", "video_paused", "ai_enabled", "ai_paused", "ai_concurrency", "priority"] as const;
export function AdminAuditPage() {
  const t = useAdminCopy(); const format = useAdminFormat(); const { page, size, update } = useAdminQuery(); const data = useAdminLoadable(() => adminApi.audit({ page, page_size: size }), [page, size]); const [detail, setDetail] = useState<AdminAudit | null>(null);
  const label = (action: string) => actionLabels[action] ? t(actionLabels[action]) : action;
  const fields: [string, string | number][] = detail ? [[t("actor"), detail.actor_id], [t("action"), label(detail.action)], [t("targets"), detail.target_ids.join(", ")], [t("reason"), detail.reason || "—"], [t("created"), format.date(detail.created_at)]] : [];
  // Explicit metadata allowlist. Never render arbitrary nested service payloads.
  if (detail) {
    for (const key of settingKeys) { const value = detail.changes[key]; if (typeof value === "number" || typeof value === "boolean") fields.push([t(key), typeof value === "boolean" ? t(value ? "yes" : "no") : value]); }
    if (typeof detail.changes.is_active === "boolean") fields.push([t("status"), t(detail.changes.is_active ? "active" : "inactive")]);
    for (const group of ["quotas", "default_quotas"]) { const values = detail.changes[group]; if (values && typeof values === "object") for (const key of quotaKeys) { const value = (values as Record<string, unknown>)[key]; if (value === null || typeof value === "number") fields.push([t(key), value === null ? t("inherited") : value]); } }
  }
  return <AdminPanel section="audit" {...data}>{data.value?.items.length ? <AdminTable label={t("audit")} headings={[t("created"), t("actor"), t("action"), t("targets"), t("reason"), t("details")]}>{data.value.items.map(item => <tr key={item.id}><td>{format.date(item.created_at)}</td><td>#{item.actor_id}</td><td>{label(item.action)}</td><td className="admin-id">{item.target_ids.join(", ") || "—"}</td><td className="admin-reason-cell">{item.reason || "—"}</td><td><AdminButton label={`${t("details")} · #${item.id}`} icon="file" onClick={() => setDetail(item)}/></td></tr>)}</AdminTable> : <AdminEmpty/>}{data.value && <AdminPager page={page} size={size} total={data.value.total} onChange={(page, page_size) => update({ page, page_size })}/>} {detail && <AdminMetadataDrawer title={`${t("details")} · #${detail.id}`} fields={fields} onClose={() => setDetail(null)}/>}</AdminPanel>;
}
