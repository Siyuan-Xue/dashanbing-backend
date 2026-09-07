import { useState } from "react";
import { adminApi, quotaKeys, type AdminSettings, type AdminUser, type QuotaKey } from "../lib/adminApi";
import { useAdminCopy } from "../lib/adminCopy";
import { AdminConfirm } from "./AdminConfirm";
import { AdminDialog } from "./AdminDialog";

export function AdminQuotaEditor({ user, settings, onClose, onSaved }: { user: AdminUser; settings: AdminSettings; onClose: () => void; onSaved: () => void }) {
  const t = useAdminCopy();
  const [values, setValues] = useState(() => Object.fromEntries(quotaKeys.map(key => [key, user.quota_overrides[key] === undefined ? "" : String(user.quota_overrides[key])])) as Record<QuotaKey, string>);
  const [review, setReview] = useState(false);
  const changes: Partial<Record<QuotaKey, number | null>> = {};
  for (const key of quotaKeys) { const next = values[key] === "" ? null : Number(values[key]); if (next !== (user.quota_overrides[key] ?? null)) changes[key] = next; }
  const valid = quotaKeys.every(key => values[key] === "" || (Number.isInteger(Number(values[key])) && Number(values[key]) >= settings.bounds.quotas[key].min && Number(values[key]) <= settings.bounds.quotas[key].max));
  const title = `${t("editQuota")} · ${user.username}`;
  if (review) return <AdminConfirm title={title} targets={[`${user.username} · #${user.id}`]} onClose={() => setReview(false)} onConfirm={async reason => { await adminApi.updateUser(user.id, { quotas: changes }, reason); onSaved(); }}><dl className="admin-metadata">{quotaKeys.filter(key => key in changes).map(key => <div key={key}><dt>{t(key)}</dt><dd>{changes[key] ?? t("inherited")}</dd></div>)}</dl></AdminConfirm>;
  return <AdminDialog title={title} onClose={onClose}><p>{t("overrideHelp")}</p><form onSubmit={event => { event.preventDefault(); if (valid && Object.keys(changes).length) setReview(true); }}><div className="admin-fields">{quotaKeys.map(key => <label className="admin-field" key={key}><span>{t(key)}</span><input aria-label={t(key)} type="number" min={settings.bounds.quotas[key].min} max={settings.bounds.quotas[key].max} step={1} value={values[key]} placeholder={`${t("inherited")} (${user.quotas[key]})`} onChange={event => setValues(current => ({ ...current, [key]: event.target.value }))}/><small>{settings.bounds.quotas[key].min}–{settings.bounds.quotas[key].max}</small></label>)}</div><footer><button className="button button-outline" type="button" onClick={onClose}>{t("cancel")}</button><button className="button button-primary" disabled={!valid || !Object.keys(changes).length}>{t("save")}</button></footer></form></AdminDialog>;
}
