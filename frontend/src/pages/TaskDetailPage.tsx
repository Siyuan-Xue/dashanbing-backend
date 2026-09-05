import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";

import { ResultWorkspace } from "../components/ResultWorkspace";
import { StatusChip } from "../components/StatusChip";
import { WorkspaceState } from "../components/WorkspaceState";
import { useLocale } from "../providers/LocaleProvider";
import { workspaceApi } from "../workspace/api";
import { taskModeLabel, taskSourceLabel, taskStageMessageLabel, taskStatusLabel } from "../workspace/labels";
import type { ProductResult, Task } from "../workspace/types";
import { useWorkspaceCopy } from "../workspace/useWorkspaceCopy";

const ACTIVE = new Set(["queued", "running"]);
const POLL_MS = 2000;

export function TaskDetailRoute() {
  const { taskId = "" } = useParams();
  return <TaskDetailPage key={taskId} taskId={taskId}/>;
}

export function TaskDetailPage({ taskId }: { taskId: string }) {
  const wt = useWorkspaceCopy();
  const { locale } = useLocale();
  const [task, setTask] = useState<Task | null>(null);
  const [taskError, setTaskError] = useState<Error | null>(null);
  const [result, setResult] = useState<ProductResult | null>(null);
  const [resultError, setResultError] = useState<Error | null>(null);
  const [resultLoading, setResultLoading] = useState(false);
  const [revision, setRevision] = useState(0);

  useEffect(() => {
    const controller = new AbortController();
    let active = true;
    let timer: ReturnType<typeof setTimeout> | undefined;
    setTask(null); setTaskError(null); setResult(null); setResultError(null); setResultLoading(false);
    const load = async () => {
      try {
        const current = await workspaceApi.getTask(taskId, controller.signal);
        if (!active) return;
        setTask(current);
        if (current.status === "completed") {
          setResultLoading(true);
          try {
            const nextResult = await workspaceApi.taskResult(taskId, controller.signal);
            if (active) setResult(nextResult);
          } catch (reason) {
            if (active && !(reason instanceof DOMException && reason.name === "AbortError")) setResultError(reason instanceof Error ? reason : new Error("Request failed"));
          } finally {
            if (active) setResultLoading(false);
          }
        } else if (ACTIVE.has(current.status)) {
          timer = setTimeout(() => { void load(); }, POLL_MS);
        }
      } catch (reason) {
        if (active && !(reason instanceof DOMException && reason.name === "AbortError")) setTaskError(reason instanceof Error ? reason : new Error("Request failed"));
      }
    };
    void load();
    return () => {
      active = false;
      controller.abort();
      if (timer) clearTimeout(timer);
    };
  }, [revision, taskId]);

  if (taskError) return <div className="workspace-page"><WorkspaceState title={wt("detailError")} body={taskError.message} onRetry={() => setRevision((value) => value + 1)}/></div>;
  if (!task) return <div className="workspace-page"><div className="loading-block page-loading" role="status" aria-label={wt("detailLoading")}/></div>;
  return <div className="workspace-page detail-page">
    <header className="detail-header"><div><Link to="/workspace/tasks" className="back-link">← {wt("tasks")}</Link><h1>{task.title}</h1><div className="detail-meta"><StatusChip status={task.status}/><span>{taskModeLabel(locale, task.mode)}</span><span>{taskSourceLabel(locale, task.source_type)}</span><span>{task.id.slice(0, 8)}</span></div></div><div className="detail-progress"><span><b>{task.progress}%</b><small>{taskStageMessageLabel(locale, task.stage_message)}</small></span><div><i style={{ width: `${task.progress}%` }}/></div></div></header>
    {task.error_message && <p className="task-error-banner" role="alert">{task.error_message}</p>}
    <ResultWorkspace key={taskId} task={task} result={result} resultLoading={resultLoading} resultError={resultError} onRetryResult={() => setRevision((value) => value + 1)} downloadUrl={task.status === "completed" && result ? `/api/v1/tasks/${task.id}/result` : undefined}/>
    <section className="task-history"><h2>{wt("timeline")}</h2><ol><li className="done"><span/><div><b>{wt("created")}</b><time>{new Date(task.created_at).toLocaleString(locale === "zh" ? "zh-CN" : "en")}</time></div></li>{task.submitted_at && <li className="done"><span/><div><b>{wt("submit")}</b><time>{new Date(task.submitted_at).toLocaleString(locale === "zh" ? "zh-CN" : "en")}</time></div></li>}{task.started_at && <li className="done"><span/><div><b>{wt("progress")}</b><time>{new Date(task.started_at).toLocaleString(locale === "zh" ? "zh-CN" : "en")}</time></div></li>}{task.completed_at && <li className="done"><span/><div><b>{taskStatusLabel(locale, task.status)}</b><time>{new Date(task.completed_at).toLocaleString(locale === "zh" ? "zh-CN" : "en")}</time></div></li>}</ol></section>
  </div>;
}
