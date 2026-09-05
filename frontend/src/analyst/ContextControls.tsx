import { WorkspaceSelect } from "../components/WorkspaceSelect";
import { useEffect, useRef, useState } from "react";
import { useLocale } from "../providers/LocaleProvider";
import { Icon } from "../components/Icon";
import { analystApi } from "./api";
import { useAnalystCopy } from "./copy";
import type { AnalystContext, AnalystSource, ContextInput, Subject, TrainingProfile } from "./types";

export function ContextControls({ source, subjects, context, subjectId, onSubject, onContext, onRetry }: { source: AnalystSource; subjects: Subject[]; context: AnalystContext | null; subjectId: string; onSubject: (id: string) => void; onContext: (value: AnalystContext) => void; onRetry: () => void }) {
  const t = useAnalystCopy(); const { locale } = useLocale();
  const [profiles, setProfiles] = useState<TrainingProfile[]>([]);
  const [error, setError] = useState(false); const [busy, setBusy] = useState(false); const [saved, setSaved] = useState(false);
  const [revision, setRevision] = useState(0);
  useEffect(() => {
    if (source.kind !== "task") return;
    const controller = new AbortController(); setError(false);
    analystApi.profiles(controller.signal).then(value => { if (!controller.signal.aborted) setProfiles(value); }).catch(() => { if (!controller.signal.aborted) setError(true); });
    return () => controller.abort();
  }, [source.kind, source.id, revision]);
  const controllerRef = useRef<AbortController | null>(null);
  useEffect(() => { const controller = new AbortController(); controllerRef.current = controller; return () => controller.abort(); }, []);
  const save = async (patch: Partial<ContextInput>) => {
    const controller = controllerRef.current;
    if (!context || busy || !controller) return;
    setBusy(true); setSaved(false); setError(false);
    const body: ContextInput = { subjects: context.subjects.map(subject => ({ id: subject.id, profile_id: subject.profile_id || null })), team_profile_id: context.team_profile_id, comparison_id: context.comparison_id, ...patch };
    try { const value = await analystApi.updateContext(source, body, controller.signal); if (!controller.signal.aborted) { onContext(value); setSaved(true); } }
    catch { if (!controller.signal.aborted) setError(true); }
    finally { if (!controller.signal.aborted) setBusy(false); }
  };
  const profileId = context?.subjects.find(subject => subject.id === subjectId)?.profile_id;
  const comparisons = context?.comparisons.filter(item => !subjectId || item.profile_id === profileId) || [];
  const outsideScope = Boolean(subjectId && context?.comparison_id && !comparisons.some(item => item.id === context.comparison_id));
  return <div className="analyst-context">
    <label className="analyst-player-select"><span>{t("player")}</span><WorkspaceSelect disabled={busy} value={subjectId} onChange={event => onSubject(event.target.value)}><option value="">{t("all")}</option>{subjects.map(subject => <option key={subject.id} value={subject.id}>{subject.label}</option>)}</WorkspaceSelect></label>
    {source.kind === "task" && context && <>
      {subjectId && <label><span>{t("linkPlayer")}</span><WorkspaceSelect disabled={busy || error} value={context.subjects.find(subject => subject.id === subjectId)?.profile_id || ""} onChange={event => void save({ subjects: context.subjects.map(subject => ({ id: subject.id, profile_id: subject.id === subjectId ? event.target.value || null : subject.profile_id || null })), comparison_id: null })}><option value="">{t("noProfile")}</option>{profiles.filter(profile => profile.kind === "player").map(profile => <option value={profile.id} key={profile.id}>{profile.name}</option>)}</WorkspaceSelect></label>}
      <label><span>{t("team")}</span><WorkspaceSelect disabled={busy || error} value={context.team_profile_id || ""} onChange={event => void save({ team_profile_id: event.target.value || null, comparison_id: null })}><option value="">{t("noProfile")}</option>{profiles.filter(profile => profile.kind === "team").map(profile => <option value={profile.id} key={profile.id}>{profile.name}</option>)}</WorkspaceSelect></label>
      <label><span>{t("compare")}</span><WorkspaceSelect disabled={busy} value={outsideScope ? "scoped" : context.comparison_id || ""} onChange={event => void save({ comparison_id: event.target.value || null })}>{outsideScope && <option value="scoped" disabled>{t("scopedComparison")}</option>}<option value="">{t("noComparison")}</option>{comparisons.map(item => <option value={item.id} key={item.id}>{profiles.find(profile => profile.id === item.profile_id)?.name || t("history")} · {new Date(item.occurred_at).toLocaleDateString(locale === "zh" ? "zh-CN" : "en")} · {item.mode}{!item.media_available && ` · ${t("metricsOnly")}`}</option>)}</WorkspaceSelect></label>
    </>}
    {source.kind === "task" && (error || !context) && <span className="analyst-context-status">{t("contextError")}<button type="button" className="table-action" aria-label={t("retry")} title={t("retry")} onClick={() => { setRevision(value => value + 1); onRetry(); }}><Icon name="refresh" size={16}/></button></span>}
    {saved && <span className="analyst-context-status" role="status"><Icon name="check" size={14}/>{t("contextSaved")}</span>}
  </div>;
}
