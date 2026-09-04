import { useCallback, useEffect, useRef, useState } from "react";
import { Link, NavLink, Outlet } from "react-router-dom";

import { Brand } from "./Brand";
import { Icon } from "./Icon";
import { useAuth } from "../providers/AuthProvider";
import { workspaceApi } from "../workspace/api";
import type { Task } from "../workspace/types";
import { useWorkspaceCopy } from "../workspace/useWorkspaceCopy";

const GITHUB_URL = "https://github.com/Siyuan-Xue/dashanbing-backend";

export function WorkspaceShell() {
  const { user } = useAuth();
  const wt = useWorkspaceCopy();
  const [open, setOpen] = useState(false);
  const [mobile, setMobile] = useState(() => window.matchMedia("(max-width: 760px)").matches);
  const [recent, setRecent] = useState<Task[]>([]);
  const menuButtonRef = useRef<HTMLButtonElement>(null);
  const firstDrawerLinkRef = useRef<HTMLAnchorElement>(null);
  const sidebarRef = useRef<HTMLElement>(null);

  const closeDrawer = useCallback(() => {
    if (!open) return;
    setOpen(false);
    requestAnimationFrame(() => menuButtonRef.current?.focus());
  }, [open]);

  useEffect(() => {
    const query = window.matchMedia("(max-width: 760px)");
    const update = (event: MediaQueryListEvent) => setMobile(event.matches);
    setMobile(query.matches);
    query.addEventListener("change", update);
    return () => query.removeEventListener("change", update);
  }, []);

  useEffect(() => {
    const params = new URLSearchParams({ page: "1", page_size: "5" });
    let active = true;
    workspaceApi.listTasks(params).then((page) => { if (active) setRecent(page.items); }).catch(() => undefined);
    return () => { active = false; };
  }, []);

  useEffect(() => {
    if (!open) return;
    firstDrawerLinkRef.current?.focus();
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === "Escape") { closeDrawer(); return; }
      if (event.key !== "Tab") return;
      const focusable = [...(sidebarRef.current?.querySelectorAll<HTMLElement>(".workspace-nav a, .workspace-recent a, .workspace-sidebar-bottom a") || [])];
      if (!focusable.length) return;
      const first = focusable[0];
      const last = focusable.at(-1)!;
      if (event.shiftKey && (document.activeElement === first || !sidebarRef.current?.contains(document.activeElement))) { event.preventDefault(); last.focus(); }
      else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); }
    };
    window.addEventListener("keydown", closeOnEscape);
    return () => window.removeEventListener("keydown", closeOnEscape);
  }, [closeDrawer, open]);

  return (
    <div className="workspace-shell">
      <button ref={menuButtonRef} className="workspace-menu-button" type="button" onClick={() => setOpen(true)} aria-label={wt("menuOpen")} aria-expanded={open} aria-controls="workspace-sidebar" inert={mobile && open ? true : undefined}><Icon name="menu"/></button>
      {open && <button className="workspace-scrim" type="button" tabIndex={-1} aria-hidden="true" onClick={closeDrawer}/>}
      <aside ref={sidebarRef} id="workspace-sidebar" className={`workspace-sidebar${open ? " is-open" : ""}`} inert={mobile && !open ? true : undefined} aria-hidden={mobile && !open ? true : undefined} role={mobile && open ? "dialog" : undefined} aria-modal={mobile && open ? true : undefined} aria-label={mobile && open ? wt("workspaceNav") : undefined}>
        <div className="workspace-brand"><Brand/></div>
        <nav className="workspace-nav" aria-label={wt("workspaceNav")} onClick={closeDrawer}>
          <NavLink ref={firstDrawerLinkRef} className="workspace-create" to="/workspace/new"><Icon name="plus"/>{wt("createTask")}</NavLink>
          <NavLink to="/workspace/tasks"><Icon name="layers"/>{wt("tasks")}</NavLink>
        </nav>
        <section className="workspace-recent" aria-labelledby="recent-heading">
          <h2 id="recent-heading">{wt("recent")}</h2>
          {recent.length ? recent.map((item) => <Link key={item.id} to={`/workspace/tasks/${item.id}`} onClick={closeDrawer}><span className={`status-dot status-${item.status}`}/><span>{item.title}</span></Link>) : <p>{wt("noRecent")}</p>}
        </section>
        <div className="workspace-sidebar-bottom">
          <Link to="/workspace/settings" className="workspace-account" onClick={closeDrawer}><span className="avatar">{user?.username.slice(0, 1).toUpperCase()}</span><span><b>{user?.username}</b><small>{wt("account")}</small></span></Link>
          <div className="workspace-utility-row">
            <a href={GITHUB_URL} target="_blank" rel="noreferrer" aria-label={wt("github")} title={wt("github")}><Icon name="github"/></a>
            <a href="/api/docs" aria-label={wt("api")} title={wt("api")}><Icon name="code"/></a>
            <Link to="/workspace/settings" aria-label={wt("settings")} title={wt("settings")}><Icon name="settings"/></Link>
          </div>
        </div>
      </aside>
      <main className="workspace-main" inert={mobile && open ? true : undefined}><Outlet/></main>
      <nav className="workspace-mobile-actions" aria-label={`${wt("workspaceNav")} mobile`} inert={mobile && open ? true : undefined}>
        <NavLink to="/workspace/new"><Icon name="plus"/><span>{wt("createTask")}</span></NavLink>
        <NavLink to="/workspace/tasks"><Icon name="layers"/><span>{wt("tasks")}</span></NavLink>
        <NavLink to="/workspace/settings"><Icon name="settings"/><span>{wt("settings")}</span></NavLink>
      </nav>
    </div>
  );
}
