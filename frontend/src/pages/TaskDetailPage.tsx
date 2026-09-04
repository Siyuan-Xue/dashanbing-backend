import { useCallback, useEffect, useRef, useState } from "react";
import { Link, useParams } from "react-router-dom";

import { Icon } from "../components/Icon";
import { ResultWorkspace } from "../components/ResultWorkspace";
import { StatusChip } from "../components/StatusChip";
import { WorkspaceState } from "../components/WorkspaceState";
import { workspaceApi } from "../workspace/api";
import type { ProductResult, Task } from "../workspace/types";
import { useWorkspaceCopy } from "../workspace/useWorkspaceCopy";

const ACTIVE = new Set(["queued", "running"]);
const POLL_MS = 2000;

export function TaskDetailPage() {
  const { taskId = "" } = useParams();
  const wt = useWorkspaceCopy();
  const [task, setTask] = useState<Task | null>(null);
  const [taskError, setTaskError] = useState<Error | null>(null);
  const [result, setResult] = useState<ProductResult | null>(null);
  const [resultError, setResultError] = useState<Error | null>(null);
  const [resultLoading, setResultLoading] = useState(false);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const generation = useRef(0);

  const loadResult = useCallback(async (requestGeneration = generation.current) => {
    setResultLoading(true); setResultError(null);
    try {
      const nextResult = await workspaceApi.taskResult(taskId);
      if (generation.current === requestGeneration) setResult(nextResult);
    } catch (reason) {
      if (generation.current === requestGeneration) setResultError(reason instanceof Error ? reason : new Error("Request failed"));
    } finally {
      if (generation.current === requestGeneration) setResultLoading(false);
    }
  }, [taskId]);

  const loadTask = useCallback(async (requestGeneration = generation.current) => {
    setTaskError(null);
    try {
      const current = await workspaceApi.getTask(taskId);
      if (generation.current !== requestGeneration) return;
      setTask(current);
      if (current.status === "completed") void loadResult(requestGeneration);
      if (ACTIVE.has(current.status)) timer.current = setTimeout(() => { void loadTask(requestGeneration); }, POLL_MS);
    } catch (reason) {
      if (generation.current === requestGeneration) setTaskError(reason instanceof Error ? reason : new Error("Request failed"));
    }
  }, [loadResult, taskId]);

  useEffect(() => {
    const requestGeneration = ++generation.current;
    void loadTask(requestGeneration);
    return () => {
      generation.current += 1;
      if (timer.current) clearTimeout(timer.current);
    };
  }, [loadTask]);

  if (taskError) return <div className="workspace-page"><WorkspaceState title={wt("detailError")} body={taskError.message} onRetry={() => void loadTask()}/></div>;
  if (!task) return <div className="workspace-page"><div className="loading-block page-loading" role="status" aria-label={wt("detailLoading")}/></div>;
  return <div className="workspace-page detail-page">
    <header className="detail-header"><div><Link to="/workspace/tasks" className="back-link">← {wt("tasks")}</Link><h1>{task.title}</h1><div className="detail-meta"><StatusChip status={task.status}/><span>{task.mode.toUpperCase()}</span><span>{task.id.slice(0, 8)}</span></div></div><div className="detail-progress"><span><b>{task.progress}%</b><small>{task.stage_message}</small></span><div><i style={{ width: `${task.progress}%` }}/></div></div></header>
    {task.error_message && <p className="task-error-banner" role="alert">{task.error_message}</p>}
    <ResultWorkspace task={task} result={result} resultLoading={resultLoading} resultError={resultError} onRetryResult={() => void loadResult()} downloadUrl={task.status === "completed" && result ? `/api/v1/tasks/${task.id}/result` : undefined}/>
    <section className="task-history"><h2>{wt("timeline")}</h2><ol><li className="done"><span/><div><b>{wt("created")}</b><time>{new Date(task.created_at).toLocaleString()}</time></div></li>{task.submitted_at && <li className="done"><span/><div><b>{wt("submit")}</b><time>{new Date(task.submitted_at).toLocaleString()}</time></div></li>}{task.started_at && <li className="done"><span/><div><b>{wt("progress")}</b><time>{new Date(task.started_at).toLocaleString()}</time></div></li>}{task.completed_at && <li className="done"><span/><div><b>{task.status}</b><time>{new Date(task.completed_at).toLocaleString()}</time></div></li>}</ol></section>
  </div>;
}
