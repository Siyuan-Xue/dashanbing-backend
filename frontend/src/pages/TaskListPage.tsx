import { FormEvent, useEffect, useMemo, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";

import { ConfirmDialog } from "../components/ConfirmDialog";
import { Icon } from "../components/Icon";
import { StatusChip } from "../components/StatusChip";
import { WorkspaceState } from "../components/WorkspaceState";
import { useLocale } from "../providers/LocaleProvider";
import { workspaceApi, WorkspaceApiError } from "../workspace/api";
import { taskModeLabel, taskStatusLabel } from "../workspace/labels";
import type { Task, TaskMode, TaskStatus } from "../workspace/types";
import { useWorkspaceCopy } from "../workspace/useWorkspaceCopy";

type Action = "cancel" | "retry" | "delete";
const statusValues: TaskStatus[] = ["draft", "uploading", "queued", "running", "completed", "failed", "canceled", "expired"];

export function TaskListPage() {
  const wt = useWorkspaceCopy();
  const { locale } = useLocale();
  const [searchParams, setSearchParams] = useSearchParams();
  const query = searchParams.toString();
  const [search, setSearch] = useState(searchParams.get("q") || "");
  const [status, setStatus] = useState(searchParams.get("status") || "");
  const [mode, setMode] = useState(searchParams.get("mode") || "");
  const [tasks, setTasks] = useState<Task[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<Error | null>(null);
  const [revision, setRevision] = useState(0);
  const [pending, setPending] = useState<{ task: Task; action: Action } | null>(null);
  const [acting, setActing] = useState(false);

  useEffect(() => {
    const current = new URLSearchParams(query);
    setSearch(current.get("q") || "");
    setStatus(current.get("status") || "");
    setMode(current.get("mode") || "");
  }, [query]);

  const page = Math.max(1, Number(searchParams.get("page") || 1));
  const pageSize = Math.max(1, Number(searchParams.get("page_size") || 10));
  const requestParams = useMemo(() => {
    const params = new URLSearchParams(query);
    params.set("page", String(page));
    params.set("page_size", String(pageSize));
    return params;
  }, [query, page, pageSize]);

  useEffect(() => {
    let active = true;
    setLoading(true);
    setError(null);
    workspaceApi.listTasks(requestParams).then((result) => {
      if (!active) return;
      setTasks(result.items); setTotal(result.total); setLoading(false);
    }).catch((reason) => { if (active) { setError(reason instanceof Error ? reason : new Error("Request failed")); setLoading(false); } });
    return () => { active = false; };
  }, [requestParams, revision]);

  const applyFilters = (event: FormEvent) => {
    event.preventDefault();
    const params = new URLSearchParams();
    if (search.trim()) params.set("q", search.trim());
    if (status) params.set("status", status);
    if (mode) params.set("mode", mode);
    params.set("page", "1");
    params.set("page_size", String(pageSize));
    setSearchParams(params);
  };

  const changePage = (nextPage: number) => {
    const params = new URLSearchParams(requestParams);
    params.set("page", String(nextPage));
    setSearchParams(params);
  };

  const execute = async () => {
    if (!pending) return;
    const selected = pending;
    setActing(true);
    try {
      if (selected.action === "delete") {
        await workspaceApi.deleteTask(selected.task.id);
      } else {
        if (selected.action === "cancel") await workspaceApi.cancelTask(selected.task.id);
        else await workspaceApi.retryTask(selected.task.id);
      }
      setPending(null);
      if (selected.action === "delete" && page > 1 && tasks.length === 1) changePage(page - 1);
      else setRevision((value) => value + 1);
    } catch (reason) {
      setPending(null);
      if (reason instanceof WorkspaceApiError && reason.status === 409) setRevision((value) => value + 1);
      else setError(reason instanceof Error ? reason : new Error("Request failed"));
    } finally { setActing(false); }
  };

  const actionButton = (item: Task, action: Action) => {
    const label = action === "cancel" ? wt("cancel") : action === "retry" ? wt("retryTask") : wt("delete");
    return <button className={`table-action action-${action}`} type="button" aria-label={`${label}${item.title}`} onClick={() => setPending({ task: item, action })}><Icon name={action === "delete" ? "trash" : action === "retry" ? "refresh" : "x"}/> {label}</button>;
  };

  const totalPages = Math.max(1, Math.ceil(total / pageSize));
  const dialogTitle = pending?.action === "cancel" ? wt("confirmCancel") : pending?.action === "retry" ? wt("confirmRetry") : wt("confirmDelete");
  const confirmLabel = `${wt("confirm")}${pending?.action === "cancel" ? wt("cancel") : pending?.action === "retry" ? wt("retryTask") : wt("delete")}`;
  return <div className="workspace-page task-list-page">
    <header className="workspace-page-header"><div><span className="page-eyebrow">TASK LIBRARY</span><h1>{wt("listTitle")}</h1><p>{wt("listBody")}</p></div><Link className="button button-primary" to="/workspace/new"><Icon name="plus"/>{wt("createTask")}</Link></header>
    <form className="task-filters" onSubmit={applyFilters}>
      <label className="search-field"><span className="sr-only">{wt("search")}</span><Icon name="search"/><input type="search" aria-label={wt("search")} value={search} onChange={(event) => setSearch(event.target.value)} placeholder={wt("search")}/></label>
      <label><span>{wt("status")}</span><select value={status} onChange={(event) => setStatus(event.target.value)}><option value="">{wt("allStatuses")}</option>{statusValues.map((value) => <option key={value} value={value}>{taskStatusLabel(locale, value)}</option>)}</select></label>
      <label><span>{wt("mode")}</span><select value={mode} onChange={(event) => setMode(event.target.value)}><option value="">{wt("allModes")}</option><option value="quick">{wt("quick")}</option><option value="full">{wt("full")}</option></select></label>
      <button className="button button-outline" type="submit">{wt("filter")}</button>
    </form>
    {error ? <WorkspaceState title={wt("loadFailed")} body={error.message} onRetry={() => setRevision((value) => value + 1)}/> : loading ? <div className="loading-block" role="status"/> : tasks.length === 0 ? <WorkspaceState title={wt("emptyTasks")}/> : <div className="task-table-wrap"><table className="task-table"><thead><tr><th>{wt("taskTitle")}</th><th>{wt("status")}</th><th>{wt("mode")}</th><th>{wt("progress")}</th><th>{wt("created")}</th><th>{wt("actions")}</th></tr></thead><tbody>{tasks.map((item) => <tr key={item.id}><td data-label={wt("taskTitle")}><Link className="task-title-link" to={`/workspace/tasks/${item.id}`}><b>{item.title}</b><small>{item.id.slice(0, 8)}</small></Link></td><td data-label={wt("status")}><StatusChip status={item.status}/></td><td data-label={wt("mode")}><span className="mode-label">{taskModeLabel(locale, item.mode)}</span></td><td data-label={wt("progress")}><div className="mini-progress"><i style={{ width: `${item.progress}%` }}/></div><span>{item.progress}%</span></td><td data-label={wt("created")}><time dateTime={item.created_at}>{new Intl.DateTimeFormat(locale === "zh" ? "zh-CN" : "en", { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" }).format(new Date(item.created_at))}</time></td><td data-label={wt("actions")}><div className="table-actions"><Link className="table-action" to={`/workspace/tasks/${item.id}`}>{wt("open")}</Link>{["draft", "uploading", "queued", "running"].includes(item.status) && actionButton(item, "cancel")}{["failed", "canceled"].includes(item.status) && actionButton(item, "retry")}{["draft", "failed", "canceled", "completed", "expired"].includes(item.status) && actionButton(item, "delete")}</div></td></tr>)}</tbody></table></div>}
    <footer className="pagination"><span>{total} · {page}/{totalPages}</span><div><button type="button" disabled={page <= 1} onClick={() => changePage(page - 1)}>{wt("previous")}</button><button type="button" disabled={page >= totalPages} onClick={() => changePage(page + 1)}>{wt("next")}</button></div></footer>
    {pending && <ConfirmDialog title={dialogTitle} message={`${pending.task.title} · ${taskStatusLabel(locale, pending.task.status)}`} confirmLabel={confirmLabel} danger={pending.action === "delete"} busy={acting} onClose={() => setPending(null)} onConfirm={() => void execute()}/>}
  </div>;
}
