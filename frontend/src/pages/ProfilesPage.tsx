import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { Icon } from "../components/Icon";
import { ConfirmDialog } from "../components/ConfirmDialog";
import { useLocale } from "../providers/LocaleProvider";
import { analystApi } from "../analyst/api";
import { useAnalystCopy } from "../analyst/copy";
import type { Observation, ProfileInput, TrainingProfile } from "../analyst/types";
import { taskModeLabel } from "../workspace/labels";

export function ProfilesPage() {
  const t = useAnalystCopy();
  const [profiles, setProfiles] = useState<TrainingProfile[]>([]); const [selectedId, setSelectedId] = useState("");
  const [loading, setLoading] = useState(true); const [error, setError] = useState(false); const [revision, setRevision] = useState(0);
  const [editing, setEditing] = useState<TrainingProfile | "new" | null>(null); const [deleting, setDeleting] = useState(false); const [busy, setBusy] = useState(false);
  const [mutationError, setMutationError] = useState(false);
  const selected = profiles.find(profile => profile.id === selectedId);
  const mounted = useRef(true);
  useEffect(() => { mounted.current = true; return () => { mounted.current = false; }; }, []);
  useEffect(() => {
    const controller = new AbortController(); setLoading(true); setError(false);
    analystApi.profiles(controller.signal).then(value => {
      if (controller.signal.aborted) return;
      setProfiles(value); setSelectedId(id => value.some(profile => profile.id === id) ? id : value[0]?.id || "");
    }).catch(() => { if (!controller.signal.aborted) setError(true); }).finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => controller.abort();
  }, [revision]);
  const remove = async () => {
    if (!selected || busy) return;
    setBusy(true); setMutationError(false);
    try {
      await analystApi.deleteProfile(selected.id);
      if (!mounted.current) return;
      const remaining = profiles.filter(profile => profile.id !== selected.id);
      setProfiles(remaining); setSelectedId(remaining[0]?.id || ""); setDeleting(false);
    } catch { if (mounted.current) setMutationError(true); }
    finally { if (mounted.current) setBusy(false); }
  };
  return <div className="workspace-page profiles-page">
    <header className="detail-header"><div className="detail-heading"><h1>{t("profiles")}</h1></div><button className="button button-primary button-icon" type="button" aria-label={t("newProfile")} title={t("newProfile")} onClick={() => setEditing("new")}><Icon name="plus"/></button></header>
    {loading ? <div className="loading-block" role="status" aria-label={t("loading")}/> : error ? <p className="analyst-error" role="alert">{t("profileError")}<button className="table-action" type="button" aria-label={t("retry")} title={t("retry")} onClick={() => setRevision(value => value + 1)}><Icon name="refresh"/></button></p> : <div className="profiles-layout">
      <nav className="profiles-list" aria-label={t("profiles")}>{profiles.map(profile => <button key={profile.id} type="button" aria-current={profile.id === selectedId ? "true" : undefined} onClick={() => { setSelectedId(profile.id); setEditing(null); setMutationError(false); }}><Icon name={profile.kind === "player" ? "user" : "team"}/><span>{profile.name}<small>{t(profile.kind === "player" ? "playerKind" : "teamKind")}</small></span></button>)}</nav>
      <div className="profile-detail">{editing ? <ProfileEditor key={typeof editing === "string" ? editing : editing.id} profile={editing === "new" ? null : editing} onClose={() => setEditing(null)} onSaved={profile => { setProfiles(values => values.some(value => value.id === profile.id) ? values.map(value => value.id === profile.id ? profile : value) : [...values, profile]); setSelectedId(profile.id); setEditing(null); }}/>
        : selected ? <><header><h2>{selected.name}</h2><div><button className="table-action" type="button" aria-label={t("editProfile")} title={t("editProfile")} onClick={() => setEditing(selected)}><Icon name="pencil"/></button><button className="table-action" type="button" aria-label={t("deleteProfile")} title={t("deleteProfile")} onClick={() => setDeleting(true)}><Icon name="trash"/></button></div></header><dl className="profile-notes"><dt>{t("goals")}</dt><dd>{selected.goals || "—"}</dd><dt>{t("notes")}</dt><dd>{selected.notes || "—"}</dd></dl><ProfileHistory key={selected.id} profileId={selected.id}/></> : <p className="analyst-muted">{t("noProfiles")}</p>}
      </div>
    </div>}
    {mutationError && <p className="analyst-error" role="alert">{t("saveError")}</p>}
    {deleting && selected && <ConfirmDialog title={t("deleteProfile")} message={mutationError ? t("saveError") : `${selected.name} · ${t("deleteBody")}`} confirmLabel={t("deleteProfile")} danger busy={busy} onConfirm={() => void remove()} onClose={() => { setDeleting(false); setMutationError(false); }}/>}
  </div>;
}
function ProfileEditor({ profile, onSaved, onClose }: { profile: TrainingProfile | null; onSaved: (value: TrainingProfile) => void; onClose: () => void }) {
  const t = useAnalystCopy();
  const [draft, setDraft] = useState<ProfileInput>({ kind: profile?.kind || "player", name: profile?.name || "", goals: profile?.goals || "", notes: profile?.notes || "" });
  const [error, setError] = useState(false); const [busy, setBusy] = useState(false);
  const active = useRef(true); const saving = useRef(false);
  useEffect(() => { active.current = true; return () => { active.current = false; }; }, []);
  const save = async () => {
    if (saving.current || !draft.name.trim()) return;
    saving.current = true; setBusy(true); setError(false);
    try {
      const body = { name: draft.name.trim(), goals: draft.goals, notes: draft.notes };
      const value = profile ? await analystApi.updateProfile(profile.id, body) : await analystApi.createProfile({ kind: draft.kind, ...body });
      if (active.current) onSaved(value);
    } catch { if (active.current) setError(true); }
    finally { if (active.current) { setBusy(false); saving.current = false; } }
  };
  return <form className="profile-editor" onSubmit={event => { event.preventDefault(); void save(); }}><h2>{t(profile ? "editProfile" : "newProfile")}</h2>
    <fieldset disabled={busy}><label><span>{t("kind")}</span><select value={draft.kind} disabled={Boolean(profile)} onChange={event => setDraft({ ...draft, kind: event.target.value as ProfileInput["kind"] })}><option value="player">{t("playerKind")}</option><option value="team">{t("teamKind")}</option></select></label>
    <label><span>{t("name")}</span><input required maxLength={120} autoFocus value={draft.name} onChange={event => setDraft({ ...draft, name: event.target.value })}/></label>
    <label><span>{t("goals")}</span><textarea rows={3} maxLength={4000} value={draft.goals} onChange={event => setDraft({ ...draft, goals: event.target.value })}/></label>
    <label><span>{t("notes")}</span><textarea rows={4} maxLength={8000} value={draft.notes} onChange={event => setDraft({ ...draft, notes: event.target.value })}/></label></fieldset>
    {error && <p className="analyst-error" role="alert">{t("saveError")}</p>}
    <div className="profile-editor-actions"><button className="button button-outline" type="button" disabled={busy} onClick={onClose}>{t("cancel")}</button><button className="button button-primary" disabled={busy || !draft.name.trim()} type="submit">{t("save")}</button></div>
  </form>;
}
function ProfileHistory({ profileId }: { profileId: string }) {
  const t = useAnalystCopy(); const { locale } = useLocale();
  const [history, setHistory] = useState<Observation[] | null>(null); const [error, setError] = useState(false); const [revision, setRevision] = useState(0);
  useEffect(() => {
    const controller = new AbortController(); setError(false);
    analystApi.history(profileId, controller.signal).then(value => { if (!controller.signal.aborted) { if (!Array.isArray(value)) throw new Error("Invalid history"); setHistory(value); } }).catch(() => { if (!controller.signal.aborted) setError(true); });
    return () => controller.abort();
  }, [profileId, revision]);
  return <section className="profile-history"><h3>{t("history")}</h3>{error ? <p className="analyst-error" role="alert">{t("profileError")}<button type="button" className="table-action" aria-label={t("retry")} title={t("retry")} onClick={() => setRevision(value => value + 1)}><Icon name="refresh"/></button></p> : !history ? <p role="status">{t("loading")}</p> : !history.length ? <p className="analyst-muted">{t("noHistory")}</p> : <ol>{history.map(item => <li key={item.id}><div><time dateTime={item.occurred_at}>{new Date(item.occurred_at).toLocaleString(locale === "zh" ? "zh-CN" : "en")}</time><span>{taskModeLabel(locale, item.mode as "quick" | "full")}</span>{item.task_id && item.media_available ? <Link className="table-action" to={`/workspace/tasks/${encodeURIComponent(item.task_id)}#analyst`} aria-label={t("openTask")} title={t("openTask")}><Icon name="arrow" size={17}/></Link> : <small>{t("metricsOnly")}</small>}</div><HistoryMetrics metrics={item.metrics}/></li>)}</ol>}</section>;
}
function HistoryMetrics({ metrics }: { metrics: Record<string, unknown> }) {
  const { locale } = useLocale();
  const shots = metrics.shots && typeof metrics.shots === "object" ? metrics.shots as Record<string, unknown> : metrics;
  const values = [[locale === "zh" ? "出手" : "Attempts", shots.attempts], [locale === "zh" ? "命中" : "Makes", shots.makes], [locale === "zh" ? "命中率" : "Make rate", typeof shots.make_rate === "number" ? `${Math.round(shots.make_rate * 100)}%` : undefined]];
  return <div className="profile-history-metrics">{values.map(([label, value]) => typeof value === "number" || typeof value === "string" ? <span key={String(label)}>{String(label)} <b>{value}</b></span> : null)}</div>;
}
