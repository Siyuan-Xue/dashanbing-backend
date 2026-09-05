import { useEffect, useState } from "react";
import { useLocale } from "../providers/LocaleProvider";
import { Icon } from "../components/Icon";
import { analystApi } from "./api";
import { AnalystChat } from "./AnalystChat";
import { ContextControls } from "./ContextControls";
import { EvidenceLinks } from "./EvidenceLinks";
import { useAnalystCopy } from "./copy";
import { useReport } from "./useReport";
import type { AnalystContext, AnalystSource, AnalystStyle, CitedText, Evidence } from "./types";

type Props = { ready?: boolean; source: AnalystSource; accountId?: number; onEvidence: (evidence: Evidence) => void };
export function AnalystAnchor() {
  const t = useAnalystCopy();
  return <a className="table-action analyst-anchor" href="#analyst" aria-label={t("jump")} title={t("jump")}><Icon name="sparkles"/></a>;
}
export function AnalystPanel(props: Props) {
  const { locale } = useLocale();
  return <AnalystSession key={`${props.accountId}:${props.source.kind}:${props.source.id}:${locale}`} {...props}/>;
}
function AnalystSession(props: Props) {
  const t = useAnalystCopy(); const [expanded, setExpanded] = useState(true); const [style, setStyle] = useState<AnalystStyle>("coach");
  useEffect(() => {
    const jump = () => { if (window.location.hash === "#analyst") { setExpanded(true); document.getElementById("analyst")?.scrollIntoView?.({ block: "start" }); } };
    jump(); window.addEventListener("hashchange", jump);
    // Re-clicking the same anchor does not fire hashchange
    const click = (event: MouseEvent) => { if (event.target instanceof Element && event.target.closest('a[href="#analyst"]')) setExpanded(true); };
    document.addEventListener("click", click);
    return () => { window.removeEventListener("hashchange", jump); document.removeEventListener("click", click); };
  }, []);
  return <section id="analyst" className="analyst-panel" aria-labelledby="analyst-heading">
    <header className="analyst-header"><h2 id="analyst-heading"><Icon name="sparkles"/>{t("title")}</h2>
      <div className="analyst-header-actions"><label className="analyst-style"><span className="sr-only">{t("style")}</span><select value={style} onChange={event => setStyle(event.target.value as AnalystStyle)}><option value="coach">{t("coach")}</option><option value="roast">{t("roast")}</option></select></label><button className="table-action" type="button" aria-controls="analyst-body" aria-expanded={expanded} aria-label={t(expanded ? "collapse" : "expand")} title={t(expanded ? "collapse" : "expand")} onClick={() => setExpanded(value => !value)}><Icon name={expanded ? "chevronDown" : "chevronRight"}/></button></div>
    </header>
    <div id="analyst-body" hidden={!expanded}><AnalystBody key={style} {...props} style={style}/></div>
  </section>;
}
function AnalystBody({ source, accountId, onEvidence, style, ready = true }: Props & { style: AnalystStyle }) {
  const t = useAnalystCopy(); const { locale } = useLocale();
  const { state, error, busy, generate, reload } = useReport(source, locale, style);
  const [context, setContext] = useState<AnalystContext | null>(null); const [contextRevision, setContextRevision] = useState(0); const [subjectId, setSubjectId] = useState("");
  useEffect(() => {
    if (source.kind !== "task") return;
    const controller = new AbortController();
    analystApi.context(source, controller.signal).then(value => { if (!controller.signal.aborted) setContext(value); }).catch(() => { if (!controller.signal.aborted) setContext(null); });
    return () => controller.abort();
  }, [source.kind, source.id, contextRevision]);
  const facts = context?.facts || state?.facts;
  const subjects = (context?.subjects || state?.subjects || []).map(subject => ({ ...subject, label: locale === "en" ? subject.label.replace(/^球员\s*(\d+)$/, "Player $1") : subject.label }));
  const evidence = facts?.evidence || [];
  const report = state?.status === "completed" ? state.report : null;
  const queued = state?.status === "queued" || state?.status === "running";
  const cited = (item: CitedText) => <><p>{item.text}</p><EvidenceLinks ids={item.evidence_ids} evidence={evidence} onEvidence={onEvidence}/></>;
  const disabled = !ready || !state || state.status === "disabled" || Boolean(error);
  const linkedProfile = context?.subjects.find(subject => subject.id === subjectId)?.profile_id;
  const selectedComparison = context?.comparisons.find(item => item.id === context.comparison_id);
  const comparisonId = !subjectId || (selectedComparison && selectedComparison.profile_id === linkedProfile) ? context?.comparison_id || null : null;
  return <>
    {(context || state?.facts) && <ContextControls source={source} context={context} subjects={subjects} subjectId={subjectId} onSubject={setSubjectId} onContext={value => { setContext(value); reload(); }} onRetry={() => setContextRevision(value => value + 1)}/>}
    <div className="analyst-columns">
      <section className="analyst-report" aria-label={t("report")} data-report-status={error ? "unavailable" : state?.status || "loading"} data-report-id={report?.id} data-report-model={report?.model}>
        <div className="analyst-report-heading"><h3>{t("report")}</h3>{source.kind === "task" && !disabled && !queued && <button className="table-action" type="button" disabled={busy} aria-label={t(report ? "regenerate" : "generate")} title={t(report ? "regenerate" : "generate")} onClick={() => void generate()}><Icon name={report ? "refresh" : "sparkles"} size={18}/></button>}</div>
        {error ? <div className="analyst-state" role="status"><Icon name="alert"/><b>{t("unavailable")}</b><button className="table-action" type="button" aria-label={t("retry")} title={t("retry")} onClick={reload}><Icon name="refresh"/></button></div> : !state ? <p className="analyst-muted" role="status">{t("loading")}</p> : report ? <>
          <p className="analyst-summary" data-report-summary>{report.summary}</p>
          {report.highlights.length > 0 && <div className="analyst-report-section"><h4>{t("highlights")}</h4><ul>{report.highlights.map((item, index) => <li key={index}>{cited(item)}</li>)}</ul></div>}
          {report.players.filter(player => !subjectId || player.subject_id === subjectId).map((player, index) => <div className="analyst-report-section" key={`${player.subject_id}:${index}`}><h4>{subjects.find(subject => subject.id === player.subject_id)?.label || player.subject_id}</h4>{cited(player)}</div>)}
          {report.comparison && (!subjectId || comparisonId !== null) && <div className="analyst-report-section"><h4>{t("comparison")}</h4>{cited(report.comparison)}</div>}
          {report.suggestions.length > 0 && <div className="analyst-report-section analyst-practice"><h4>{t("suggestions")}</h4><ol>{report.suggestions.map((suggestion, index) => <li key={index}>{suggestion}</li>)}</ol></div>}
          <footer className="analyst-provenance">{report.model} · <time dateTime={report.created_at}>{new Date(report.created_at).toLocaleString(locale === "zh" ? "zh-CN" : "en")}</time></footer>
        </> : <div className="analyst-state" role="status"><Icon name={state.status === "disabled" ? "sparkles" : "clock"}/><b>{t(state.status === "waiting" && source.kind === "preset" ? "presetWaiting" : state.status === "completed" ? "unavailable" : state.status)}</b>{state.error && <p>{state.error}</p>}</div>}
        {facts?.warnings.map((warning, index) => <p className="analyst-warning" key={index}>{warning}</p>)}
      </section>
      <AnalystChat source={source} accountId={accountId} style={style} subjectId={subjectId} comparisonId={comparisonId} evidence={evidence} onEvidence={onEvidence} disabled={disabled}/>
    </div>
  </>;
}
