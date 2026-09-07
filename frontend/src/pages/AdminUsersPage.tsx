import { useState } from "react";
import { adminApi, quotaKeys, type AdminUser } from "../lib/adminApi";
import { useAdminCopy } from "../lib/adminCopy";
import { useAdminLoadable } from "../lib/adminLoadable";
import { AdminConfirm } from "../components/AdminConfirm";
import { AdminMetadataDrawer } from "../components/AdminMetadataDrawer";
import { AdminQuotaEditor } from "../components/AdminQuotaEditor";
import { AdminButton, AdminEmpty, AdminFilters, AdminPager, AdminPanel, AdminTable, useAdminFormat, useAdminQuery } from "../components/AdminShared";

export function AdminUsersPage() {
  const t = useAdminCopy(); const format = useAdminFormat(); const { params, page, size, update } = useAdminQuery(); const q = params.get("q") || ""; const status = params.get("is_active") || "";
  const data = useAdminLoadable(() => Promise.all([adminApi.users({ page, page_size: size, q, is_active: status }), adminApi.settings()]), [page, size, q, status]);
  const [pending, setPending] = useState<{ user: AdminUser; action: "status" | "revoke" | "quota" } | null>(null);
  const [detail, setDetail] = useState<AdminUser | null>(null);
  const [saved, setSaved] = useState(false);
  const users = data.value?.[0]; const settings = data.value?.[1];
  function changed() { setPending(null); setSaved(true); data.reload(); }
  const label = pending ? t(pending.action === "revoke" ? "revoke" : pending.user.is_active ? "disable" : "enable") : "";
  return <AdminPanel section="users" {...data}>
    <AdminFilters search={q} values={{ is_active: status }} options={[{ key: "is_active", label: t("status"), values: [{ value: "true", label: t("active") }, { value: "false", label: t("inactive") }] }]} onApply={values => { update({ ...values, page: 1 }); setSaved(false); }}/>
    {saved && <p className="admin-notice" role="status">{t("saved")}</p>}
    {users?.items.length ? <AdminTable label={t("users")} headings={[t("username"), t("status"), t("usage"), t("created"), t("actions")]}>{users.items.map(user => <tr key={user.id}><td className="admin-user-identity"><strong>{user.username}</strong><small>{user.email || "—"} · #{user.id}</small></td><td><span className={`admin-status${user.is_active ? "" : " is-warning"}`}>{t(user.is_active ? "active" : "inactive")}</span></td><td><div className="admin-usage-grid">{quotaKeys.map(key => <span key={key} title={t(key)}><span>{t(key)}</span><b>{format.number(user.usage[key])} / {format.number(user.quotas[key])}</b></span>)}</div></td><td>{format.date(user.created_at)}</td><td><div className="admin-actions"><AdminButton icon="file" label={`${t("details")} · ${user.username}`} onClick={() => setDetail(user)}/><AdminButton icon="pencil" label={`${t("editQuota")} · ${user.username}`} onClick={() => { setSaved(false); setPending({ user, action: "quota" }); }}/><AdminButton icon={user.is_active ? "ban" : "check"} danger={user.is_active} label={`${t(user.is_active ? "disable" : "enable")} · ${user.username}`} onClick={() => { setSaved(false); setPending({ user, action: "status" }); }}/><AdminButton icon="logout" danger label={`${t("revoke")} · ${user.username}`} onClick={() => { setSaved(false); setPending({ user, action: "revoke" }); }}/></div></td></tr>)}</AdminTable> : <AdminEmpty clear={q || status ? () => update({ q: "", is_active: "", page: 1 }) : undefined}/>}
    {users && <AdminPager page={page} size={size} total={users.total} onChange={(page, page_size) => update({ page, page_size })}/>}
    {pending && pending.action !== "quota" && <AdminConfirm title={label} targets={[`${pending.user.username} · #${pending.user.id}`]} onClose={() => setPending(null)} onConfirm={async reason => { if (pending.action === "revoke") await adminApi.revokeSessions(pending.user.id, reason); else await adminApi.updateUser(pending.user.id, { is_active: !pending.user.is_active }, reason); changed(); }}>{(pending.action === "revoke" || pending.user.is_active) && <p>{t(pending.action === "revoke" ? "revokedHelp" : "disableHelp")}</p>}</AdminConfirm>}
    {pending?.action === "quota" && settings && <AdminQuotaEditor user={pending.user} settings={settings} onClose={() => setPending(null)} onSaved={changed}/>}
    {detail && <AdminMetadataDrawer title={`${t("details")} · ${detail.username}`} fields={[[t("userId"), detail.id], [t("username"), detail.username], [t("email"), detail.email || "—"], [t("role"), t("ordinary")], [t("status"), t(detail.is_active ? "active" : "inactive")], [t("created"), format.date(detail.created_at)], ...quotaKeys.map(key => [t(key), `${detail.usage[key]} / ${detail.quotas[key]}`] as [string, string])]} onClose={() => setDetail(null)}/>}
  </AdminPanel>;
}
