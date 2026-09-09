import { NavLink } from "react-router-dom";
import { useAdminCopy } from "../lib/adminCopy";
import { AdminAccountMenu } from "./AdminAccountMenu";
import { Icon } from "./Icon";
import { WorkspaceFrame } from "./WorkspaceFrame";
import "../styles/admin.css";

export function AdminShell() {
  const wt = useAdminCopy();
  return <WorkspaceFrame sidebarId="admin-sidebar" className="admin-shell"
    labels={{ expand: wt("expand"), collapse: wt("collapse"), menuOpen: wt("menuOpen"), menuClose: wt("menuClose"), navigation: wt("navigation") }}
    navigation={firstLink => <nav className="workspace-nav" aria-label={wt("navigation")}>
      {([ ["overview", "chart"], ["users", "team"], ["scheduling", "layers"], ["quotas", "settings"], ["operations", "activity"], ["audit", "file"] ] as const).map(([section, icon], index) => <NavLink ref={index === 0 ? firstLink : undefined} key={section} to={`/admin/${section}`} aria-label={wt(section)}><Icon name={icon}/><span>{wt(section)}</span></NavLink>)}
    </nav>}
    footer={<AdminAccountMenu/>}
  />;
}
