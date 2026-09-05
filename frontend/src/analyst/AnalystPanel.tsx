import { useEffect, useRef, useState } from "react";
import { useLocale } from "../providers/LocaleProvider";
import { Icon } from "../components/Icon";
import { WorkspaceSelect } from "../components/WorkspaceSelect";
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
  const [style, setStyle] = useState<AnalystStyle>("coach");
  useEffect(() => {
    const jump = () => { if (window.location.hash === "#analyst") { document.getElementById("analyst")?.scrollIntoView?.({ block: "start" }); } };
    jump(); window.addEventListener("hashchange", jump);
    return () => window.removeEventListener("hashchange", jump);
  }, []);
  return <section id="analyst" className="analyst-panel" aria-labelledby="analyst-heading">
    <AnalystBody {...props} style={style} onStyle={setStyle}/>

  </section>;
}
function AnalystBody({ source, accountId, onEvidence, style, onStyle, ready = true }: Props & { style: AnalystStyle; onStyle: (value: AnalystStyle) => void }) {
  const t = useAnalystCopy(); const { locale } = useLocale();
  const { state, error, busy, generate, reload } = useReport(source, locale, style, ready);
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
    <header className="analyst-header">
      <h2 id="analyst-heading"><Icon name="sparkles"/>{t("title")}</h2>
      <AnalystSettings>
        {(context || state?.facts) && <ContextControls source={source} context={context} subjects={subjects} subjectId={subjectId} onSubject={setSubjectId} onContext={value => { setContext(value); reload(); }} onRetry={() => setContextRevision(value => value + 1)}/>}
        <label className="analyst-style"><span>{t("style")}</span><WorkspaceSelect value={style} onChange={event => onStyle(event.target.value as AnalystStyle)}><option value="coach">{t("coach")}</option><option value="roast">{t("roast")}</option></WorkspaceSelect></label>
      </AnalystSettings>
    </header>
    <div id="analyst-body"><div className="analyst-columns">
      <section className="analyst-report" aria-label={t("report")} data-report-status={error ? "unavailable" : state?.status || "loading"} data-report-id={report?.id} data-report-model={report?.model}>
        <div className="analyst-report-heading"><h3 className="sr-only">{t("report")}</h3>{source.kind === "task" && !disabled && !queued && <button className="table-action" type="button" disabled={busy} aria-label={t(report ? "regenerate" : "generate")} title={t(report ? "regenerate" : "generate")} onClick={() => void generate()}><Icon name={report ? "refresh" : "sparkles"} size={18}/></button>}</div>
        {error ? <div className="analyst-state" role="status"><Icon name="alert"/><b>{t("unavailable")}</b><button className="table-action" type="button" aria-label={t("retry")} title={t("retry")} onClick={reload}><Icon name="refresh"/></button></div> : !state ? <p className="analyst-muted" role="status">{t("loading")}</p> : report ? <>
          <p className="analyst-summary" data-report-summary>{report.summary}</p>
          <div className="analyst-report-grid"><div className="analyst-evidence-column">
          {report.highlights.length > 0 && <div className="analyst-report-section"><h4>{t("highlights")}</h4><ul className="analyst-key-plays">{report.highlights.map((item, index) => <li key={index}><span className="analyst-play-index" aria-hidden="true">{String(index + 1).padStart(2, "0")}</span><div>{cited(item)}</div></li>)}</ul></div>}
          {report.players.filter(player => !subjectId || player.subject_id === subjectId).map((player, index) => <div className="analyst-report-section" key={`${player.subject_id}:${index}`}><h4>{subjects.find(subject => subject.id === player.subject_id)?.label || player.subject_id}</h4>{cited(player)}</div>)}
          {report.comparison && (!subjectId || comparisonId !== null) && <div className="analyst-report-section"><h4>{t("comparison")}</h4>{cited(report.comparison)}</div>}
          </div>
          {report.suggestions.length > 0 && <div className="analyst-report-section analyst-practice"><h4>{t("suggestions")}</h4><ol>{report.suggestions.map((suggestion, index) => <li key={index}>{suggestion}</li>)}</ol></div>}
          </div>
        </> : <div className="analyst-state" role="status"><Icon name={state.status === "disabled" ? "sparkles" : "clock"}/><b>{t(state.status === "waiting" && source.kind === "preset" ? "presetWaiting" : state.status === "completed" ? "unavailable" : state.status)}</b>{state.error && <p>{state.error}</p>}</div>}
      </section>
      <AnalystChat source={source} accountId={accountId} style={style} subjectId={subjectId} comparisonId={comparisonId} evidence={evidence} onEvidence={onEvidence} disabled={disabled}/>
    </div></div>
  </>;
}

function AnalystSettings({ children }: { children: React.ReactNode }) {
  const t = useAnalystCopy(); const [open, setOpen] = useState(false);
  const [placement, setPlacement] = useState({ above: false, maxHeight: 400 });
  const root = useRef<HTMLDivElement>(null); const trigger = useRef<HTMLButtonElement>(null);
  useEffect(() => {
    if (!open) return;
    const position = () => {
      const anchor = root.current?.getBoundingClientRect();
      const panel = root.current?.querySelector<HTMLElement>('[role="dialog"]');
      if (!anchor || !panel) return;
      const below = window.innerHeight - anchor.bottom - 20;
      const above = anchor.top - 20;
      const showAbove = below < panel.scrollHeight && above > below;
      setPlacement({ above: showAbove, maxHeight: Math.max(80, showAbove ? above : below) });
    };
    position();
    root.current?.querySelector("select")?.focus({ preventScroll: true });
    const dismiss = (event: KeyboardEvent) => {
      if (event.key === "Escape") { event.preventDefault(); setOpen(false); trigger.current?.focus(); }
    };
    const outside = (event: PointerEvent) => { if (!root.current?.contains(event.target as Node)) setOpen(false); };
    window.addEventListener("keydown", dismiss); window.addEventListener("pointerdown", outside);
    window.addEventListener("resize", position); window.addEventListener("scroll", position, true);
    return () => { window.removeEventListener("keydown", dismiss); window.removeEventListener("pointerdown", outside); window.removeEventListener("resize", position); window.removeEventListener("scroll", position, true); };
  }, [open]);
  return <div className="task-filter-control analyst-settings" ref={root} onBlur={event => { if (event.relatedTarget && !event.currentTarget.contains(event.relatedTarget)) setOpen(false); }}>
    <button className="button" type="button" ref={trigger} aria-expanded={open} aria-controls="analyst-settings" aria-haspopup="dialog" onClick={() => setOpen(value => !value)}><Icon name="filter" size={16}/>{t("configure")}</button>
    <div className="task-filter-popover analyst-settings-popover" id="analyst-settings" role="dialog" aria-label={t("configure")} hidden={!open} style={{ top: placement.above ? "auto" : undefined, bottom: placement.above ? "calc(100% + 10px)" : undefined, maxHeight: placement.maxHeight }}>{children}</div>
  </div>;
}
