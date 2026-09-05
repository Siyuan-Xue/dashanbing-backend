import { useEffect, useRef, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { Icon } from "../components/Icon";
import { ConfirmDialog } from "../components/ConfirmDialog";
import { ProfileEditor } from "../components/ProfileEditor";
import { WorkspaceState } from "../components/WorkspaceState";
import { useLocale } from "../providers/LocaleProvider";
import { analystApi } from "../analyst/api";
import { useAnalystCopy } from "../analyst/copy";
import type { Observation, TrainingProfile } from "../analyst/types";
import { taskModeLabel } from "../workspace/labels";
import "../styles/profiles.css";

export function ProfileDetailPage() {
  const { profileId = "" } = useParams();
  return <ProfileDetail key={profileId} profileId={profileId}/>;
}
function ProfileDetail({ profileId }: { profileId: string }) {
  const t = useAnalystCopy(); const { locale } = useLocale(); const navigate = useNavigate();
  const [profile, setProfile] = useState<TrainingProfile | null>(null);
  const [loading, setLoading] = useState(true); const [error, setError] = useState(false); const [revision, setRevision] = useState(0);
  const [editing, setEditing] = useState(false); const [deleting, setDeleting] = useState(false); const [busy, setBusy] = useState(false); const [mutationError, setMutationError] = useState(false);
  const mounted = useRef(true); const removing = useRef(false);
  useEffect(() => { mounted.current = true; return () => { mounted.current = false; }; }, []);
  useEffect(() => {
    const controller = new AbortController(); setLoading(true); setError(false);
    analystApi.profiles(controller.signal).then(values => { if (!controller.signal.aborted) setProfile(values.find(value => value.id === profileId) || null); })
      .catch(() => { if (!controller.signal.aborted) setError(true); })
      .finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => controller.abort();
  }, [profileId, revision]);
  const remove = async () => {
    if (!profile || removing.current) return;
    removing.current = true; setBusy(true); setMutationError(false);
    try {
      await analystApi.deleteProfile(profile.id);
      if (mounted.current) navigate("/workspace/profiles", { replace: true });
    } catch { if (mounted.current) setMutationError(true); }
    finally { removing.current = false; if (mounted.current) setBusy(false); }
  };
  const backLabel = locale === "zh" ? "返回档案列表" : "Back to profiles";
  return <div className="workspace-page profile-detail-page">
    {loading ? <div className="loading-block" role="status" aria-label={t("loading")}/> : error ? <WorkspaceState title={t("profileError")} onRetry={() => setRevision(value => value + 1)}/>
      : !profile ? <WorkspaceState icon="user" title={locale === "zh" ? "未找到档案" : "Profile not found"} body={locale === "zh" ? "此档案可能已被删除，返回列表查看其他档案。" : "This profile may have been deleted. Return to the list to find another profile."} action={<Link className="button button-outline" to="/workspace/profiles">{backLabel}</Link>}/>
      : <>
        <header className="detail-header"><div className="detail-heading"><Link className="back-link" to="/workspace/profiles" aria-label={backLabel} title={backLabel}><Icon name="chevronLeft"/></Link><h1>{profile.name}</h1></div><div className="detail-actions"><button className="table-action" type="button" aria-label={t("editProfile")} title={t("editProfile")} onClick={() => setEditing(true)}><Icon name="pencil"/></button><button className="table-action action-delete" type="button" aria-label={t("deleteProfile")} title={t("deleteProfile")} onClick={() => { setMutationError(false); setDeleting(true); }}><Icon name="trash"/></button></div></header>
        <dl className="profile-notes"><dt>{t("kind")}</dt><dd>{t(profile.kind === "player" ? "playerKind" : "teamKind")}</dd><dt>{t("goals")}</dt><dd>{profile.goals || "—"}</dd><dt>{t("notes")}</dt><dd>{profile.notes || "—"}</dd><dt>{locale === "zh" ? "更新时间" : "Updated"}</dt><dd><time dateTime={profile.updated_at}>{new Date(profile.updated_at).toLocaleString(locale === "zh" ? "zh-CN" : "en")}</time></dd></dl>
        <ProfileHistory profileId={profile.id}/>
        {editing && <ProfileEditor profile={profile} onSaved={value => { setProfile(value); setEditing(false); }} onClose={() => setEditing(false)}/>}
        {deleting && <ConfirmDialog title={t("deleteProfile")} message={mutationError ? t("saveError") : `${profile.name} · ${t("deleteBody")}`} confirmLabel={t("deleteProfile")} danger busy={busy} onConfirm={() => void remove()} onClose={() => { setDeleting(false); setMutationError(false); }}/>}
      </>}
  </div>;
}
function ProfileHistory({ profileId }: { profileId: string }) {
  const t = useAnalystCopy(); const { locale } = useLocale();
  const [history, setHistory] = useState<Observation[] | null>(null); const [error, setError] = useState(false); const [revision, setRevision] = useState(0);
  useEffect(() => {
    const controller = new AbortController(); setError(false); setHistory(null);
    analystApi.history(profileId, controller.signal).then(value => { if (!controller.signal.aborted) { if (!Array.isArray(value)) throw new Error("Invalid history"); setHistory(value); } }).catch(() => { if (!controller.signal.aborted) setError(true); });
    return () => controller.abort();
  }, [profileId, revision]);
  return <section className="profile-history"><h3>{t("history")}</h3>{error ? <WorkspaceState title={t("profileError")} onRetry={() => setRevision(value => value + 1)}/> : !history ? <p role="status">{t("loading")}</p> : !history.length ? <WorkspaceState icon="activity" title={t("noHistory")} body={locale === "zh" ? "在已完成任务的 AI 分析师中绑定此档案，即可积累训练记录。" : "Bind this profile in a completed task’s AI analyst to start tracking training history."} action={<Link className="button button-outline" to="/workspace/tasks">{locale === "zh" ? "查看任务" : "View tasks"}</Link>}/> : <ol>{history.map(item => <li key={item.id}><div><time dateTime={item.occurred_at}>{new Date(item.occurred_at).toLocaleString(locale === "zh" ? "zh-CN" : "en")}</time><span>{taskModeLabel(locale, item.mode as "quick" | "full")}</span>{item.task_id && item.media_available ? <Link className="table-action" to={`/workspace/tasks/${encodeURIComponent(item.task_id)}#analyst`} aria-label={t("openTask")} title={t("openTask")}><Icon name="arrow" size={17}/></Link> : <small>{t("metricsOnly")}</small>}</div><HistoryMetrics metrics={item.metrics}/></li>)}</ol>}</section>;
}
function HistoryMetrics({ metrics }: { metrics: Record<string, unknown> }) {
  const { locale } = useLocale();
  const shots = metrics.shots && typeof metrics.shots === "object" ? metrics.shots as Record<string, unknown> : metrics;
  const values = [[locale === "zh" ? "出手" : "Attempts", shots.attempts], [locale === "zh" ? "命中" : "Makes", shots.makes], [locale === "zh" ? "命中率" : "Make rate", typeof shots.make_rate === "number" ? `${Math.round(shots.make_rate * 100)}%` : undefined]];
  return <div className="profile-history-metrics">{values.map(([label, value]) => typeof value === "number" || typeof value === "string" ? <span key={String(label)}>{String(label)} <b>{value}</b></span> : null)}</div>;
}
