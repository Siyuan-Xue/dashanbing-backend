import type { ReactNode } from "react";
import { useWorkspaceCopy } from "../workspace/useWorkspaceCopy";
import { Icon } from "./Icon";

export function WorkspaceSidebarFooter({ account, settings, tools }: { account: ReactNode; settings?: ReactNode; tools?: ReactNode }) {
  const wt = useWorkspaceCopy();
  return <div className="workspace-sidebar-bottom">
    {account}
    <div className="workspace-utility-row">
      {tools ?? <><a href="https://github.com/Siyuan-Xue/dashanbing-backend" target="_blank" rel="noreferrer" aria-label={wt("github")} title={wt("github")}><Icon name="github" size={18}/></a>
      <a href="/api/docs" aria-label={wt("api")} title={wt("api")}><Icon name="code" size={18}/></a>
      {settings}</>}
    </div>
  </div>;
}
