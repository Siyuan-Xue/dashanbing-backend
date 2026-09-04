import { useEffect, useMemo, useState } from "react";

import { localizeResultMessage } from "../localization";
import { useLocale } from "../providers/LocaleProvider";
import { actionLabel, outcomeLabel, taskStageMessageLabel } from "../workspace/labels";
import type { ProductResult, Task } from "../workspace/types";
import { useWorkspaceCopy } from "../workspace/useWorkspaceCopy";

const mediaKinds = ["phases", "cam_01", "cam_02", "cam_03", "cam_04"] as const;

export function ResultWorkspace({ task, result, resultLoading = false, resultError, onRetryResult, downloadUrl }: {
  task?: Task; result: ProductResult | null; resultLoading?: boolean; resultError?: Error | null; onRetryResult?: () => void; downloadUrl?: string;
}) {
  const wt = useWorkspaceCopy();
  const { locale } = useLocale();
  const availableKinds = useMemo(() => result ? mediaKinds.filter((kind) => Boolean(result.media[kind])) : [], [result]);
  const [mediaKind, setMediaKind] = useState<(typeof mediaKinds)[number]>("phases");
  const [rightTab, setRightTab] = useState<"summary" | "timeline" | "json">("summary");
  useEffect(() => {
    if (result && !result.media[mediaKind] && availableKinds[0]) setMediaKind(availableKinds[0]);
  }, [availableKinds, mediaKind, result]);
  const mediaLabels = { phases: wt("phases"), cam_01: wt("cam1"), cam_02: wt("cam2"), cam_03: wt("cam3"), cam_04: wt("cam4") };
  const statusMessage = task ? ({
    draft: wt("draftBody"), uploading: wt("uploadingBody"), queued: wt("queuedBody"), running: wt("runningBody"),
    completed: wt("emptyResult"), failed: task.error_message || wt("failedBody"), canceled: wt("canceledBody"), expired: wt("expiredBody"),
  })[task.status] : wt("emptyResult");

  return <div className="result-workspace">
    <section className="result-media-panel">
      <div className="media-tabs" role="tablist" aria-label={wt("mediaViews")}>{mediaKinds.map((kind) => <button key={kind} role="tab" aria-selected={mediaKind === kind} disabled={result ? !result.media[kind] : false} onClick={() => setMediaKind(kind)}>{mediaLabels[kind]}</button>)}</div>
      <div className="media-stage">
        {result?.media[mediaKind] ? <video key={result.media[mediaKind]} controls preload="metadata" src={result.media[mediaKind]} title={`${mediaLabels[mediaKind]}${locale === "en" ? " player" : " 播放器"}`}/> : <div className="media-placeholder"><span className="court-lines" aria-hidden="true"/><div>{task && ["queued", "running"].includes(task.status) ? <><span className="analysis-orbit"/><b>{taskStageMessageLabel(locale, task.stage_message)}</b><p>{task.progress}% · {statusMessage}</p></> : <><span aria-hidden="true">▶</span><b>{resultLoading ? wt("resultLoading") : wt("mediaUnavailable")}</b></>}</div></div>}
      </div>
    </section>
    <section className="result-insights-panel">
      <div className="insight-tabs" role="tablist" aria-label={wt("resultViews")}><button role="tab" aria-selected={rightTab === "summary"} onClick={() => setRightTab("summary")}>{wt("summary")}</button><button role="tab" aria-selected={rightTab === "timeline"} onClick={() => setRightTab("timeline")}>{wt("timeline")}</button><button role="tab" aria-selected={rightTab === "json"} onClick={() => setRightTab("json")}>{wt("json")}</button></div>
      <div className="insight-content">
        {resultError ? <div className="inline-result-state" role="alert"><b>{wt("resultUnavailable")}</b><p>{resultError.message}</p>{onRetryResult && <button onClick={onRetryResult}>{wt("tryAgain")}</button>}</div> : resultLoading ? <div className="loading-block" role="status"/> : result ? <>
          {rightTab === "summary" && <div className="result-summary"><div className="result-stat-grid"><article><span>{wt("attempts")}</span><b>{result.shots.attempts}</b></article><article><span>{wt("makes")}</span><b>{result.shots.makes}</b></article><article><span>{wt("participants")}</span><b>{result.registered_participant_count}</b></article><article><span>{wt("actionsCount")}</span><b>{result.events.length}</b></article></div><div className="make-rate"><span><b>{Math.round((result.shots.make_rate || 0) * 100)}%</b><small>MAKE RATE</small></span></div><div className="action-breakdown">{Object.entries(result.action_counts).map(([name, count]) => <div key={name}><span>{actionLabel(locale, name as keyof typeof result.action_counts)}</span><b>{count}</b></div>)}</div>{(result.warnings || []).map((warning, index) => <p className="result-warning" key={`${warning}-${index}`}>{localizeResultMessage(locale, warning)}</p>)}<p className="result-disclaimer">{localizeResultMessage(locale, result.disclaimer)}</p></div>}
          {rightTab === "timeline" && <ol className="event-timeline">{result.events.length ? result.events.map((event) => <li key={event.event_index}><time>{(event.time_ms / 1000).toFixed(1)}s</time><span><b>{actionLabel(locale, event.action_type)}</b><small>{outcomeLabel(locale, event.result)} · {(event.start_ms / 1000).toFixed(1)}–{(event.end_ms / 1000).toFixed(1)}s</small></span></li>) : <li>{wt("emptyResult")}</li>}</ol>}
          {rightTab === "json" && <pre className="result-json">{JSON.stringify(result, null, 2)}</pre>}
        </> : <div className="inline-result-state"><b>{task ? taskStageMessageLabel(locale, task.stage_message) : wt("emptyResult")}</b><p>{task ? statusMessage : wt("emptyResult")}</p></div>}
      </div>
      {result && downloadUrl && <a className="result-download" href={downloadUrl} download aria-label={wt("downloadJson")}><span>JSON</span>{wt("downloadJson")} <b aria-hidden="true">↓</b></a>}
    </section>
  </div>;
}
