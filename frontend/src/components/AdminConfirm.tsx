import { useId, useRef, useState, type ReactNode } from "react";
import { adminErrorKey } from "../lib/adminApi";
import { useAdminCopy } from "../lib/adminCopy";
import { AdminDialog } from "./AdminDialog";
import { Icon } from "./Icon";

export function AdminConfirm({ title, targets, children, onConfirm, onClose }: { title: string; targets: string[]; children?: ReactNode; onConfirm: (reason: string) => Promise<void>; onClose: () => void }) {
  const t = useAdminCopy(); const id = useId();
  const [reason, setReason] = useState("");
  const [acknowledged, setAcknowledged] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const inFlight = useRef(false);
  const valid = reason.trim().length >= 3 && reason.trim().length <= 500 && acknowledged;
  async function submit() {
    if (!valid || inFlight.current) return;
    inFlight.current = true; setBusy(true); setError(null);
    try { await onConfirm(reason.trim()); } catch (error) { setError(error); }
    finally { inFlight.current = false; setBusy(false); }
  }
  return <AdminDialog title={title} busy={busy} onClose={onClose}><form onSubmit={event => { event.preventDefault(); void submit(); }}>
    <ul className="admin-targets">{targets.map(target => <li key={target}>{target}</li>)}</ul>
    {children}
    <label className="admin-field" htmlFor={id}><span>{t("reason")}</span><textarea id={id} value={reason} disabled={busy} maxLength={500} aria-describedby={`${id}-hint`} onChange={event => setReason(event.target.value)} required/></label><p id={`${id}-hint`} className="admin-hint">{t("reasonHint")}</p>
    <label className="admin-acknowledge"><input type="checkbox" checked={acknowledged} disabled={busy} onChange={event => setAcknowledged(event.target.checked)}/><span>{t("acknowledge")}</span></label>
    {Boolean(error) && <p className="admin-error" role="alert">{t(adminErrorKey(error))}</p>}
    <footer><button className="button button-outline" type="button" disabled={busy} onClick={onClose}>{t("cancel")}</button><button className="button button-primary" type="submit" disabled={busy || !valid}>{busy && <Icon name="refresh" spin/>}{t(busy ? "working" : "confirm")}</button></footer>
  </form></AdminDialog>;
}
