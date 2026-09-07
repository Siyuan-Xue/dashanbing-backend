import { useState } from "react";
import { adminApi, quotaKeys, type AdminSettings, type SettingsPatch, type SettingsValues } from "../lib/adminApi";
import { useAdminCopy } from "../lib/adminCopy";
import { AdminConfirm } from "./AdminConfirm";

const switches = ["video_enabled", "video_paused", "ai_enabled", "ai_paused"] as const;
export function AdminSettingsForm({ settings, mode, onSaved }: { settings: AdminSettings; mode: "quotas" | "scheduling"; onSaved: () => void }) {
  const t = useAdminCopy(); const [values, setValues] = useState<SettingsValues>(settings.current); const [concurrency, setConcurrency] = useState(String(settings.current.ai_concurrency)); const [quotaValues, setQuotaValues] = useState(() => Object.fromEntries(quotaKeys.map(key => [key, String(settings.current.default_quotas[key])])));
  const [review, setReview] = useState(false);
  const changes: SettingsPatch = {};
  if (mode === "scheduling") { for (const key of switches) if (values[key] !== settings.current[key]) changes[key] = values[key]; }
  else {
    if (Number(concurrency) !== settings.current.ai_concurrency) changes.ai_concurrency = Number(concurrency);
    for (const key of quotaKeys) if (Number(quotaValues[key]) !== settings.current.default_quotas[key]) { changes.default_quotas ||= {}; changes.default_quotas[key] = Number(quotaValues[key]); }
  }
  const validNumber = (value: string, min: number, max: number) => value.trim() !== "" && Number.isInteger(Number(value)) && Number(value) >= min && Number(value) <= max;
  const valid = mode === "scheduling" || (validNumber(concurrency, settings.bounds.ai_concurrency.min, settings.bounds.ai_concurrency.max) && quotaKeys.every(key => validNumber(quotaValues[key], settings.bounds.quotas[key].min, settings.bounds.quotas[key].max)));
  return <section className="admin-settings"><h2>{t(mode === "quotas" ? "defaultQuotas" : "schedulingSettings")}</h2><p className="admin-hint">{t(mode === "quotas" ? "quotaHelp" : "admissionHelp")}</p><form onSubmit={event => { event.preventDefault(); if (valid && Object.keys(changes).length) setReview(true); }}>
    {mode === "scheduling" ? <div className="admin-switches">{switches.map(key => <label key={key}><input type="checkbox" checked={values[key]} onChange={event => setValues(current => ({ ...current, [key]: event.target.checked }))}/><span>{t(key)}</span></label>)}</div> : <div className="admin-fields">{quotaKeys.map(key => <label className="admin-field" key={key}><span>{t(key)}</span><input aria-label={t(key)} type="number" step={1} required min={settings.bounds.quotas[key].min} max={settings.bounds.quotas[key].max} value={quotaValues[key]} onChange={event => setQuotaValues(current => ({ ...current, [key]: event.target.value }))}/><small>{settings.bounds.quotas[key].min}–{settings.bounds.quotas[key].max}</small></label>)}<label className="admin-field"><span>{t("ai_concurrency")}</span><input aria-label={t("ai_concurrency")} type="number" step={1} required min={settings.bounds.ai_concurrency.min} max={settings.bounds.ai_concurrency.max} value={concurrency} onChange={event => setConcurrency(event.target.value)}/><small>{settings.bounds.ai_concurrency.min}–{settings.bounds.ai_concurrency.max}</small></label></div>}
    <div className="admin-form-actions"><button className="button button-primary" type="submit" disabled={!valid || !Object.keys(changes).length}>{t("save")}</button></div>
  </form>{review && <AdminConfirm title={t("save")} targets={[t(mode === "quotas" ? "quotas" : "schedulingSettings")]} onClose={() => setReview(false)} onConfirm={async reason => { await adminApi.updateSettings(changes, reason); onSaved(); }}><dl className="admin-metadata">{switches.filter(key => key in changes).map(key => <div key={key}><dt>{t(key)}</dt><dd>{t(changes[key] ? "yes" : "no")}</dd></div>)}{changes.ai_concurrency !== undefined && <div><dt>{t("ai_concurrency")}</dt><dd>{settings.current.ai_concurrency} → {changes.ai_concurrency}</dd></div>}{quotaKeys.filter(key => changes.default_quotas?.[key] !== undefined).map(key => <div key={key}><dt>{t(key)}</dt><dd>{settings.current.default_quotas[key]} → {changes.default_quotas?.[key]}</dd></div>)}</dl></AdminConfirm>}</section>;
}
