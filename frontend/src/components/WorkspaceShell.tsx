import { useEffect, useState } from "react";
import { Link, NavLink } from "react-router-dom";
import { useAnalystCopy } from "../analyst/copy";
import { useAuth } from "../providers/AuthProvider";
import { workspaceApi } from "../workspace/api";
import type { Task } from "../workspace/types";
import { useWorkspaceCopy } from "../workspace/useWorkspaceCopy";
import { Icon } from "./Icon";
import { StatusChip } from "./StatusChip";
import { WorkspaceFrame } from "./WorkspaceFrame";
import { WorkspaceSidebarFooter } from "./WorkspaceSidebarFooter";

export function WorkspaceShell() {
  const { user } = useAuth();
  const wt = useWorkspaceCopy();
  const at = useAnalystCopy();
  const [recent, setRecent] = useState<Task[]>([]);
  useEffect(() => {
    let active = true;
    workspaceApi.listTasks({ page: 1, page_size: 5 }).then(page => { if (active) setRecent(page.items); }).catch(() => undefined);
    return () => { active = false; };
  }, []);
  return <WorkspaceFrame sidebarId="workspace-sidebar"
    labels={{ expand: wt("sidebarExpand"), collapse: wt("sidebarCollapse"), menuOpen: wt("menuOpen"), menuClose: wt("menuClose"), navigation: wt("workspaceNav") }}
    navigation={firstDrawerLinkRef => <nav className="workspace-nav" aria-label={wt("workspaceNav")}>
          <NavLink ref={firstDrawerLinkRef} className="workspace-create" to="/workspace/new" aria-label={wt("createTask")} ><Icon name="plus"/><span>{wt("createTask")}</span></NavLink>
          <NavLink to="/workspace/tasks" aria-label={wt("tasks")} ><Icon name="layers"/><span>{wt("tasks")}</span></NavLink>
          <NavLink to="/workspace/profiles" aria-label={at("profiles")} ><Icon name="team"/><span>{at("profiles")}</span></NavLink>
        </nav>}
    footer={<WorkspaceSidebarFooter
      account={<Link to="/workspace/settings" className="workspace-account" aria-label={`${wt("account")}${wt("labelSeparator")}${user?.username || ""}`} title={user?.username}><span className="workspace-avatar"><Icon name="user" size={18}/></span></Link>}
      settings={<Link to="/workspace/settings" aria-label={wt("settings")} title={wt("settings")}><Icon name="settings" size={18}/></Link>}
    />}>
    <section className="workspace-recent" aria-labelledby="recent-heading">
          <h2 id="recent-heading">{wt("recent")}</h2>
          {recent.length ? recent.map((item) => <Link key={item.id} to={`/workspace/tasks/${item.id}`} title={item.title} aria-label={item.title} aria-describedby={`recent-status-${item.id}`}><StatusChip id={`recent-status-${item.id}`} status={item.status} stageMessage={item.stage_message} compact/><span>{item.title}</span></Link>) : <p>{wt("noRecent")}</p>}
        </section>
  </WorkspaceFrame>;
}
