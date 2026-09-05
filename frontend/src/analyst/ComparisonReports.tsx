import { useEffect, useRef, useState } from "react";
import { Icon } from "../components/Icon";
import { WorkspaceSelect } from "../components/WorkspaceSelect";
import { useLocale } from "../providers/LocaleProvider";
import { analystApi } from "./api";
import { useAnalystCopy } from "./copy";
import { EvidenceLinks } from "./EvidenceLinks";
import { useComparisons } from "./useComparisons";
import type { AnalystContext, AnalystSource, AnalystStyle, Evidence, Observation, TrainingProfile } from "./types";

export function ComparisonReports({ source, context, style, disabled, onEvidence }: {
  source: AnalystSource; context: AnalystContext; style: AnalystStyle; disabled: boolean; onEvidence: (evidence: Evidence) => void;
}) {
  const t = useAnalystCopy(); const { locale } = useLocale();
  const contextKey = JSON.stringify([context.subjects, context.team_profile_id, context.comparisons]);
  const { items, error, busy, append, reload } = useComparisons(source, locale, style, contextKey);
  const linked = new Set([context.team_profile_id, ...context.subjects.map(subject => subject.profile_id)].filter(Boolean));
  const candidates = context.comparisons.filter(item => linked.has(item.profile_id));
  const [open, setOpen] = useState(false), [selected, setSelected] = useState("");
  const [profiles, setProfiles] = useState<TrainingProfile[]>([]);
  const root = useRef<HTMLDivElement>(null), trigger = useRef<HTMLButtonElement>(null);
  const [above, setAbove] = useState(false);
  const [maxHeight, setMaxHeight] = useState(400);
  useEffect(() => { setOpen(false); }, [contextKey, style]);
  useEffect(() => {
    if (!open) return;
    const controller = new AbortController();
    analystApi.profiles(controller.signal).then(value => { if (!controller.signal.aborted) setProfiles(value); }).catch(() => {});
    const position = () => {
      const box = root.current?.getBoundingClientRect(); if (!box) return;
      const below = innerHeight - box.bottom - 16, over = box.top - 16;
      const placeAbove = below < 260 && over > below;
      setAbove(placeAbove); setMaxHeight(Math.max(80, placeAbove ? over : below));
    };
    position(); root.current?.querySelector("select")?.focus({ preventScroll: true });
    const close = (event: KeyboardEvent) => { if (event.key === "Escape") { event.preventDefault(); setOpen(false); trigger.current?.focus(); } };
    const outside = (event: PointerEvent) => { if (!root.current?.contains(event.target as Node)) setOpen(false); };
    window.addEventListener("keydown", close); window.addEventListener("pointerdown", outside);
    window.addEventListener("resize", position); window.addEventListener("scroll", position, true);
    return () => { controller.abort(); window.removeEventListener("keydown", close); window.removeEventListener("pointerdown", outside); window.removeEventListener("resize", position); window.removeEventListener("scroll", position, true); };
  }, [open]);
  const date = (item: Observation) => new Date(item.occurred_at).toLocaleDateString(locale === "zh" ? "zh-CN" : "en");
  const label = (item: Observation) => {
    const subject = context.subjects.find(subject => subject.profile_id === item.profile_id);
    const name = profiles.find(profile => profile.id === item.profile_id)?.name || (subject ? locale === "en" ? subject.label.replace(/^球员\s*(\d+)$/, "Player $1") : subject.label : t("teamKind"));
    return `${name} · ${date(item)}${!item.media_available ? ` · ${t("metricsOnly")}` : ""}`;
  };
  const generate = async () => {
    if (disabled || !candidates.some(item => item.id === selected)) return;
    if (await append(selected)) { setOpen(false); trigger.current?.focus({ preventScroll: true }); }
  };
  if (!candidates.length && !items.length) return null;
  return <section className="analyst-comparisons" aria-label={t("comparisonReports")}>
    <header className="analyst-comparison-heading">
      {items.length > 0 && <h3>{t("comparisonReports")}</h3>}
      {candidates.length > 0 && <div className="analyst-comparison-control task-filter-control" ref={root} onBlur={event => { if (event.relatedTarget && !event.currentTarget.contains(event.relatedTarget)) setOpen(false); }}>
        <button type="button" className="button" ref={trigger} disabled={disabled || busy} aria-expanded={open} aria-haspopup="dialog" onClick={() => { setSelected(candidates.find(item => !items.some(report => report.comparison_id === item.id))?.id || candidates[0].id); setOpen(value => !value); }}><Icon name="chart" size={16}/>{t("compareTraining")}</button>
        {open && <form className="task-filter-popover analyst-comparison-picker" role="dialog" aria-label={t("compareTraining")} style={{ top: above ? "auto" : undefined, bottom: above ? "calc(100% + 10px)" : undefined, maxHeight }} onSubmit={event => { event.preventDefault(); void generate(); }}>
          <label><span>{t("historicalSession")}</span><WorkspaceSelect value={selected} disabled={busy} onChange={event => setSelected(event.target.value)}>{candidates.map(item => <option value={item.id} key={item.id}>{label(item)}</option>)}</WorkspaceSelect></label>
          <p className="analyst-config-help">{t("appendComparisonHelp")}</p>
          {error && <p className="analyst-error" role="alert">{t("comparisonError")}</p>}
          <button className="button button-primary" type="submit" disabled={disabled || busy || !selected}>{t("generateComparison")}</button>
        </form>}
      </div>}
    </header>
    {error && !open && <p className="analyst-error" role="alert">{t("comparisonError")}<button className="table-action" type="button" aria-label={t("retryComparison")} title={t("retryComparison")} onClick={reload}><Icon name="refresh" size={16}/></button></p>}
    <div className="analyst-comparison-list">{items.map(item => {
      const history = context.comparisons.find(history => history.id === item.comparison_id);
      const report = item.status === "completed" ? item.report : null;
      return <article className="analyst-comparison-report" key={item.comparison_id} data-comparison-id={item.comparison_id} data-comparison-status={item.status}>
        <h4>{history ? label(history) : t("historicalSession")}</h4>
        {report ? <>
          <p className="analyst-comparison-summary">{report.summary}</p>
          {report.comparison && <p>{report.comparison.text}<EvidenceLinks ids={report.comparison.evidence_ids} evidence={context.facts.evidence} onEvidence={onEvidence}/></p>}
          {report.highlights.length > 0 && <ul>{report.highlights.map((point, index) => <li key={index}>{point.text}<EvidenceLinks ids={point.evidence_ids} evidence={context.facts.evidence} onEvidence={onEvidence}/></li>)}</ul>}
          {report.players.map((player, index) => <p key={`${player.subject_id}:${index}`}>{player.text}<EvidenceLinks ids={player.evidence_ids} evidence={context.facts.evidence} onEvidence={onEvidence}/></p>)}
          {report.suggestions.length > 0 && <div className="analyst-comparison-practice"><h5>{t("suggestions")}</h5><ul>{report.suggestions.map((point, index) => <li key={index}>{point}</li>)}</ul></div>}
        </> : <p className="analyst-muted" role="status">{t(item.status === "completed" ? "unavailable" : item.status)}{item.status === "failed" && <button type="button" className="table-action" disabled={disabled || busy || !history} aria-label={t("retryComparison")} title={t("retryComparison")} onClick={() => void append(item.comparison_id)}><Icon name="refresh" size={16}/></button>}</p>}
      </article>;
    })}</div>
  </section>;
}
