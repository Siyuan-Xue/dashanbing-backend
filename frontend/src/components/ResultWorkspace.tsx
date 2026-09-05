import { useEffect, useId, useMemo, useRef, useState } from "react";
import type { KeyboardEvent } from "react";

import { Icon } from "./Icon";

import { localizeResultMessage } from "../localization";
import { useLocale } from "../providers/LocaleProvider";
import { actionLabel, outcomeLabel, taskStageMessageLabel } from "../workspace/labels";
import type { ProductResult, Task } from "../workspace/types";
import { useWorkspaceCopy } from "../workspace/useWorkspaceCopy";

const mediaKinds = ["phases", "cam_01", "cam_02", "cam_03", "cam_04"] as const;
const insightKinds = ["summary", "timeline", "json"] as const;

// Arrow keys skip unavailable views; Tab leaves the tablist for its panel.
function navigateTabs(event: KeyboardEvent<HTMLDivElement>) {
  if (!["ArrowLeft", "ArrowRight", "Home", "End"].includes(event.key)) return;
  const tabs = [...event.currentTarget.querySelectorAll<HTMLButtonElement>('button:not(:disabled)')];
  const index = tabs.indexOf(document.activeElement as HTMLButtonElement);
  if (index < 0 || !tabs.length) return;
  event.preventDefault();
  const next = event.key === "Home" ? 0 : event.key === "End" ? tabs.length - 1 : (index + (event.key === "ArrowRight" ? 1 : -1) + tabs.length) % tabs.length;
  tabs[next].focus();
  tabs[next].click();
}

function ResultVideo({ src, title }: { src: string; title: string }) {
  const wt = useWorkspaceCopy();
  const [state, setState] = useState<"loading" | "ready" | "error">("loading");
  const [attempt, setAttempt] = useState(0);
  return <>
    {state !== "error" && <video key={attempt} controls autoPlay muted playsInline preload="auto" src={src} title={title} onLoadedMetadata={() => setState("ready")} onLoadedData={() => setState("ready")} onCanPlay={() => setState("ready")} onError={() => setState("error")}/>}
    {state === "loading" && <span className="media-loading" role="status">{wt("mediaLoading")}</span>}
    {state === "error" && <div className="media-placeholder" role="alert"><div><b>{wt("mediaError")}</b><button type="button" className="media-retry" aria-label={wt("reloadMedia")} title={wt("reloadMedia")} onClick={() => { setAttempt((value) => value + 1); setState("loading"); }}><Icon name="refresh"/></button></div></div>}
  </>;
}

export function ResultWorkspace({ task, result, resultLoading = false, resultError, onRetryResult, downloadUrl }: {
  task?: Task; result: ProductResult | null; resultLoading?: boolean; resultError?: Error | null; onRetryResult?: () => void; downloadUrl?: string;
}) {
  const wt = useWorkspaceCopy();
  const { locale } = useLocale();
  const id = useId();
  const availableKinds = useMemo(() => result ? mediaKinds.filter((kind) => Boolean(result.media[kind])) : [], [result]);
  const [mediaKind, setMediaKind] = useState<(typeof mediaKinds)[number]>("phases");
  const [rightTab, setRightTab] = useState<(typeof insightKinds)[number]>("summary");
  useEffect(() => {
    if (result && !result.media[mediaKind] && availableKinds[0]) setMediaKind(availableKinds[0]);
  }, [availableKinds, mediaKind, result]);
  const insightRef = useRef<HTMLDivElement>(null);
  useEffect(() => { if (insightRef.current) insightRef.current.scrollTop = 0; }, [rightTab]);
  const mediaLabels = { phases: wt("phases"), cam_01: wt("cam1"), cam_02: wt("cam2"), cam_03: wt("cam3"), cam_04: wt("cam4") };
  const statusMessage = task ? ({
    draft: wt("draftBody"), uploading: wt("uploadingBody"), queued: wt("queuedBody"), running: wt("runningBody"),
    completed: wt("emptyResult"), failed: task.error_message || wt("failedBody"), canceled: wt("canceledBody"), expired: wt("expiredBody"),
  })[task.status] : wt("emptyResult");
  const src = result?.media[mediaKind];

  return <div className="result-workspace">
    <section className="result-media-panel" aria-label={wt("mediaViews")}>
      <div className="media-tabs" role="tablist" aria-label={wt("mediaViews")} onKeyDown={navigateTabs}>
        {mediaKinds.map((kind) => <button key={kind} id={`${id}-${kind}`} type="button" role="tab" aria-selected={mediaKind === kind} aria-controls={`${id}-media-panel`} tabIndex={mediaKind === kind ? 0 : -1} disabled={!result?.media[kind]} onClick={() => setMediaKind(kind)}>{mediaLabels[kind]}</button>)}
      </div>
      <div id={`${id}-media-panel`} className="media-stage" role="tabpanel" aria-labelledby={`${id}-${mediaKind}`} tabIndex={0}>
        {src ? <ResultVideo key={src} src={src} title={`${mediaLabels[mediaKind]}${locale === "en" ? " player" : " 播放器"}`}/> : <div className="media-placeholder"><div>{task && ["queued", "running"].includes(task.status) ? <><span className="analysis-orbit" aria-hidden="true"/><b>{taskStageMessageLabel(locale, task.stage_message)}</b><p>{task.progress}%</p></> : <><span className="media-empty-icon" aria-hidden="true">▷</span><b>{resultLoading ? wt("resultLoading") : wt("mediaUnavailable")}</b></>}</div></div>}
      </div>
    </section>
    <section className="result-insights-panel" aria-label={wt("resultViews")}>
      <div className="insight-tabs" role="tablist" aria-label={wt("resultViews")} onKeyDown={navigateTabs}>
        {insightKinds.map((tab) => <button key={tab} type="button" id={`${id}-${tab}`} role="tab" aria-selected={rightTab === tab} aria-controls={`${id}-insight-panel`} tabIndex={rightTab === tab ? 0 : -1} onClick={() => setRightTab(tab)}>{wt(tab)}</button>)}
      </div>
      <div id={`${id}-insight-panel`} ref={insightRef} className={`insight-content${rightTab !== "summary" ? " has-alternate" : ""}`} role="tabpanel" aria-labelledby={`${id}-${rightTab}`} tabIndex={0}>
        {resultError ? <div className="inline-result-state" role="alert"><b>{wt("resultUnavailable")}</b><p>{resultError.message}</p>{onRetryResult && <button className="button button-outline button-icon" type="button" aria-label={wt("tryAgain")} title={wt("tryAgain")} onClick={onRetryResult}><Icon name="refresh"/></button>}</div> : resultLoading ? <div className="loading-block" role="status" aria-label={wt("resultLoading")}/> : result ? <>
          <div className={`result-summary${rightTab !== "summary" ? " is-inactive" : ""}`} aria-hidden={rightTab !== "summary" ? true : undefined} inert={rightTab !== "summary" ? true : undefined}>
            <div className="result-stat-grid"><article><span>{wt("attempts")}</span><b>{result.shots.attempts}</b></article><article><span>{wt("makes")}</span><b>{result.shots.makes}</b></article><article><span>{wt("participants")}</span><b>{result.registered_participant_count}</b></article><article><span>{wt("actionsCount")}</span><b>{result.events.length}</b></article></div>
            <div className="make-rate"><span>{wt("makeRate")}</span><b>{Math.round((result.shots.make_rate || 0) * 100)}%</b></div>
            <div className="action-breakdown">{Object.entries(result.action_counts).map(([name, count]) => <div key={name}><span>{actionLabel(locale, name as keyof typeof result.action_counts)}</span><b>{count}</b></div>)}</div>
            {(result.warnings || []).map((warning, index) => <p className="result-warning" key={`${warning}-${index}`}>{localizeResultMessage(locale, warning)}</p>)}
            <p className="result-disclaimer">{localizeResultMessage(locale, result.disclaimer)}</p>
          </div>
          {rightTab === "timeline" && <div className="insight-alternate" tabIndex={0}><ol className="event-timeline">{result.events.length ? result.events.map((event) => <li key={event.event_index}><time>{(event.time_ms / 1000).toFixed(1)}s</time><span><b>{actionLabel(locale, event.action_type)}</b><small>{outcomeLabel(locale, event.result)} · {(event.start_ms / 1000).toFixed(1)}–{(event.end_ms / 1000).toFixed(1)}s</small></span></li>) : <li>{wt("emptyResult")}</li>}</ol></div>}
          {rightTab === "json" && <div className="insight-alternate" tabIndex={0}><pre className="result-json" tabIndex={0}>{JSON.stringify(result, null, 2)}</pre></div>}
        </> : <div className="inline-result-state"><b>{task ? taskStageMessageLabel(locale, task.stage_message) : wt("emptyResult")}</b><p>{statusMessage}</p></div>}
      </div>
      {result && downloadUrl && <a className="result-download" href={downloadUrl} download aria-label={wt("downloadJson")} title={wt("downloadJson")}><Icon name="download"/></a>}
    </section>
  </div>;
}
