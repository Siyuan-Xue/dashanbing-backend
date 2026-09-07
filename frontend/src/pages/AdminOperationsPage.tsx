import { adminApi } from "../lib/adminApi";
import { useAdminCopy } from "../lib/adminCopy";
import { useAdminLoadable } from "../lib/adminLoadable";
import { AdminPanel } from "../components/AdminShared";
import { AdminResources } from "../components/AdminResources";
export function AdminOperationsPage() { const t = useAdminCopy(); const data = useAdminLoadable(() => Promise.all([adminApi.deployment(), adminApi.overview()])); const deployment = data.value?.[0]; return <AdminPanel section="operations" {...data}>{deployment && data.value && <><span className="admin-readonly">{t("readOnly")}</span><dl className="admin-metadata admin-deployment"><div><dt>{t("version")}</dt><dd>{deployment.application.version}</dd></div><div><dt>{t("databaseRevision")}</dt><dd>{deployment.application.database_revision || t("unknown")}</dd></div><div><dt>{t("videoWorker")}</dt><dd>{t(deployment.workers.video_enabled ? "enabled" : "disabled")}</dd></div><div><dt>{t("aiWorker")}</dt><dd>{t(deployment.workers.ai_enabled ? "enabled" : "disabled")}</dd></div><div><dt>{t("backupStatus")}</dt><dd>{t("unknown")}</dd></div></dl><AdminResources value={data.value[1].resources}/></>}</AdminPanel>; }
