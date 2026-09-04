import { useWorkspaceCopy } from "../workspace/useWorkspaceCopy";

export function WorkspaceState({ title, body, onRetry }: { title: string; body?: string; onRetry?: () => void }) {
  const wt = useWorkspaceCopy();
  return <div className="workspace-state" role={onRetry ? "alert" : "status"}><span className="workspace-state-mark" aria-hidden="true">!</span><h2>{title}</h2>{body && <p>{body}</p>}{onRetry && <button className="button button-outline" onClick={onRetry}>{wt("tryAgain")}</button>}</div>;
}
