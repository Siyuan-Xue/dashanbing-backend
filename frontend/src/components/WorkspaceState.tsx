import type { ReactNode } from "react";
import { Icon, type IconName } from "./Icon";
import { useWorkspaceCopy } from "../workspace/useWorkspaceCopy";

export function WorkspaceState({ title, body, onRetry, action, icon = "file" }: {
  title: string; body?: string; onRetry?: () => void; action?: ReactNode; icon?: IconName;
}) {
  const wt = useWorkspaceCopy();
  return <div className="workspace-state" role={onRetry ? "alert" : "status"}>
    <span className="workspace-state-mark"><Icon name={onRetry ? "alert" : icon}/></span>
    <h2>{title}</h2>{body && <p>{body}</p>}
    {onRetry && <button type="button" className="button button-outline button-icon" aria-label={wt("tryAgain")} title={wt("tryAgain")} onClick={onRetry}><Icon name="refresh"/></button>}
    {action}
  </div>;
}
