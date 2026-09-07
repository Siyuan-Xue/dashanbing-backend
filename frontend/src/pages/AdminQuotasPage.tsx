import { useState } from "react";
import { Link } from "react-router-dom";
import { adminApi } from "../lib/adminApi";
import { useAdminCopy } from "../lib/adminCopy";
import { useAdminLoadable } from "../lib/adminLoadable";
import { AdminPanel } from "../components/AdminShared";
import { AdminSettingsForm } from "../components/AdminSettingsForm";
import { AdminRepairBudget } from "../components/AdminRepairBudget";
export function AdminQuotasPage() { const t = useAdminCopy(); const data = useAdminLoadable(adminApi.settings); const [saved, setSaved] = useState(false); return <AdminPanel section="quotas" {...data}>{saved && <p role="status" className="admin-notice">{t("saved")}</p>}{data.value && <><AdminSettingsForm settings={data.value} mode="quotas" onSaved={() => { setSaved(true); data.reload(); }}/><Link className="admin-inline-link" to="/admin/users">{t("users")} · {t("editQuota")}</Link><AdminRepairBudget value={data.value.repair_budget}/></>}</AdminPanel>; }
