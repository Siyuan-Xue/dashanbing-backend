import { useEffect, useState } from "react";
import { adminApi, type AdminJob, type JobAction } from "../lib/adminApi";
import { useAdminCopy, type AdminCopyKey } from "../lib/adminCopy";
import { useAdminLoadable } from "../lib/adminLoadable";
import { AdminConfirm } from "../components/AdminConfirm";
import { AdminMetadataDrawer } from "../components/AdminMetadataDrawer";
import { AdminSettingsForm } from "../components/AdminSettingsForm";
import { AdminRepairBudget } from "../components/AdminRepairBudget";
import { AdminButton, AdminEmpty, AdminFilters, AdminPager, AdminPanel, AdminStatus, AdminTable, useAdminFormat, useAdminQuery } from "../components/AdminShared";
import type { IconName } from "../components/Icon";

const actions: { action: JobAction; label: AdminCopyKey; icon: IconName }[] = [{ action: "hold", label: "holdSelected", icon: "stop" }, { action: "release", label: "releaseSelected", icon: "play" }, { action: "priority", label: "prioritySelected", icon: "layers" }, { action: "retry", label: "retrySelected", icon: "refresh" }, { action: "backfill", label: "backfillSelected", icon: "plus" }];
export function AdminSchedulingPage() {
  const t = useAdminCopy(); const format = useAdminFormat(); const { params, page, size, update } = useAdminQuery(); const kind = params.get("kind") || ""; const status = params.get("status") || "";
  const data = useAdminLoadable(() => Promise.all([adminApi.jobs({ page, page_size: size, kind, status }), adminApi.settings()]), [page, size, kind, status]);
  const [selected, setSelected] = useState<AdminJob[]>([]); const [priority, setPriority] = useState("0"); const [detail, setDetail] = useState<AdminJob | null>(null); const [saved, setSaved] = useState(false);
  const [pending, setPending] = useState<{ jobs: AdminJob[]; action: JobAction; label: AdminCopyKey; priority?: number } | null>(null);
  useEffect(() => { setSelected([]); setSaved(false); }, [page, size, kind, status]);
  const jobs = data.value?.[0]; const settings = data.value?.[1]; const limit = Math.min(10, settings?.bounds.batch_size || 10);
  const refresh = () => { setSelected([]); data.reload(); };
  const changed = () => { setPending(null); setSaved(true); refresh(); };
  const priorityValid = !!settings && priority.trim() !== "" && Number.isInteger(Number(priority)) && Number(priority) >= settings.bounds.priority.min && Number(priority) <= settings.bounds.priority.max;
  function eligible(action: JobAction) { return selected.length > 0 && selected.length <= limit && selected.every(job => job.kind === selected[0].kind && job.allowed_actions.includes(action)) && (action !== "priority" || priorityValid); }
  return <AdminPanel section="scheduling" {...data} reload={refresh}>
    {settings && <AdminSettingsForm settings={settings} mode="scheduling" onSaved={changed}/>}
    <AdminFilters values={{ kind, status }} options={[{ key: "kind", label: t("kind"), values: (["video", "ai", "preset"] as const).map(value => ({ value, label: t(value) })) }, { key: "status", label: t("status"), values: (["queued", "running", "failed", "completed", "interrupted", "canceled"] as const).map(value => ({ value, label: t(value) })) }]} onApply={values => update({ ...values, page: 1 })}/>
    {saved && <p role="status" className="admin-notice">{t("saved")}</p>}
    <div className="admin-batch"><div><span>{t("selected")} {selected.length} / {limit}</span><small>{t("batchHint")}</small></div><div className="admin-actions">{actions.map(item => <AdminButton key={item.action} label={t(item.label)} icon={item.icon} danger={item.action === "hold" || item.action === "retry" || item.action === "backfill"} disabled={!eligible(item.action)} onClick={() => { setSaved(false); setPending({ jobs: [...selected], action: item.action, label: item.label, ...(item.action === "priority" ? { priority: Number(priority) } : {}) }); }}/>)}</div>{settings && <label className="admin-priority"><span>{t("priority")}</span><input type="number" step={1} min={settings.bounds.priority.min} max={settings.bounds.priority.max} value={priority} onChange={event => setPriority(event.target.value)}/></label>}</div>
    {jobs?.items.length ? <AdminTable label={t("scheduling")} headings={[t("select"), t("taskId"), t("kind"), t("status"), t("priority"), t("updated"), t("actions")]}>{jobs.items.map(job => { const checked = selected.some(item => item.kind === job.kind && item.id === job.id); const disabled = !checked && (selected.length >= limit || !!selected.length && selected[0].kind !== job.kind || !job.allowed_actions.length); return <tr key={`${job.kind}:${job.id}`}><td><input type="checkbox" aria-label={`${t("select")} · ${job.id}`} checked={checked} disabled={disabled} onChange={() => setSelected(current => checked ? current.filter(item => !(item.kind === job.kind && item.id === job.id)) : [...current, job])}/></td><td><strong className="admin-id">{job.id}</strong><small>{t("owner")}: {job.owner_id ?? "—"}</small></td><td>{t(job.kind)}</td><td><AdminStatus status={job.status}/>{job.held && <small>{t("held")}</small>}</td><td>{job.priority}</td><td>{format.date(job.updated_at)}</td><td><AdminButton label={`${t("details")} · ${job.id}`} icon="file" onClick={() => setDetail(job)}/></td></tr>; })}</AdminTable> : <AdminEmpty clear={kind || status ? () => update({ kind: "", status: "", page: 1 }) : undefined}/>}
    {jobs && <AdminPager page={page} size={size} total={jobs.total} onChange={(page, page_size) => update({ page, page_size })}/>}
    {settings && <AdminRepairBudget value={settings.repair_budget}/>}
    {pending && <AdminConfirm title={t(pending.label)} targets={pending.jobs.map(job => `${t(job.kind)} · ${job.id}`)} onClose={() => setPending(null)} onConfirm={async reason => { await adminApi.act({ kind: pending.jobs[0].kind, ids: pending.jobs.map(job => job.id), action: pending.action, ...(pending.priority !== undefined ? { priority: pending.priority } : {}) }, reason); changed(); }}>{pending.priority !== undefined && <p>{t("priority")}: {pending.priority}</p>}{["retry", "backfill"].includes(pending.action) && <p>{t("repairHelp")}</p>}</AdminConfirm>}
    {detail && <AdminMetadataDrawer title={`${t("details")} · ${detail.id}`} fields={[[t("taskId"), detail.id], [t("kind"), t(detail.kind)], [t("owner"), detail.owner_id ?? "—"], [t("status"), detail.status], [t("held"), t(detail.held ? "yes" : "no")], [t("priority"), detail.priority], [t("attempts"), detail.attempts], [t("adminRetries"), detail.admin_retries], [t("created"), format.date(detail.created_at)], [t("updated"), format.date(detail.updated_at)]]} onClose={() => setDetail(null)}/>}
  </AdminPanel>;
}
