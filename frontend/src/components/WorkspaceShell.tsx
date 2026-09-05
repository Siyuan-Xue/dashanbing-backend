import { useCallback, useEffect, useRef, useState } from "react";
import { Link, NavLink, Outlet, useLocation } from "react-router-dom";

import { Brand } from "./Brand";
import { Icon } from "./Icon";
import { StatusChip } from "./StatusChip";
import { useAuth } from "../providers/AuthProvider";
import { workspaceApi } from "../workspace/api";
import type { Task } from "../workspace/types";
import { useWorkspaceCopy } from "../workspace/useWorkspaceCopy";

const GITHUB_URL = "https://github.com/Siyuan-Xue/dashanbing-backend";
const MOBILE_QUERY = "(max-width: 767px)";

export function WorkspaceShell() {
  const { user } = useAuth();
  const wt = useWorkspaceCopy();
  const location = useLocation();
  const [peek, setPeek] = useState(false);
  const hoverClose = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);
  const [open, setOpen] = useState(false);
  const [mobile, setMobile] = useState(() => window.matchMedia(MOBILE_QUERY).matches);
  const [collapsed, setCollapsed] = useState(() => window.matchMedia("(min-width: 768px) and (max-width: 1279px)").matches);
  const [recent, setRecent] = useState<Task[]>([]);
  const menuButtonRef = useRef<HTMLButtonElement>(null);
  const collapseButtonRef = useRef<HTMLButtonElement>(null);
  const firstDrawerLinkRef = useRef<HTMLAnchorElement>(null);
  const sidebarRef = useRef<HTMLElement>(null);
  const rail = collapsed && !mobile;

  const keepPeek = () => clearTimeout(hoverClose.current);
  const hidePeekSoon = () => {
    keepPeek();
    hoverClose.current = setTimeout(() => {
      if (!sidebarRef.current?.contains(document.activeElement)) setPeek(false);
    }, 160);
  };
  const togglePinned = () => {
    keepPeek();
    setPeek(false);
    setCollapsed(value => !value);
    requestAnimationFrame(() => collapseButtonRef.current?.focus());
  };
  useEffect(() => {
    setPeek(false);
    clearTimeout(hoverClose.current);
  }, [location.pathname, location.search]);
  useEffect(() => () => clearTimeout(hoverClose.current), []);
  useEffect(() => {
    if (!rail || !peek) return;
    const dismiss = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        event.preventDefault(); setPeek(false); collapseButtonRef.current?.focus();
      }
    };
    const outside = (event: PointerEvent) => {
      if (!sidebarRef.current?.contains(event.target as Node) && !collapseButtonRef.current?.contains(event.target as Node)) setPeek(false);
    };
    window.addEventListener("keydown", dismiss);
    window.addEventListener("pointerdown", outside);
    return () => { window.removeEventListener("keydown", dismiss); window.removeEventListener("pointerdown", outside); };
  }, [rail, peek]);

  const closeDrawer = useCallback(() => {
    if (!open) return;
    setOpen(false);
    requestAnimationFrame(() => menuButtonRef.current?.focus());
  }, [open]);

  useEffect(() => {
    const query = window.matchMedia(MOBILE_QUERY);
    const update = (event: MediaQueryListEvent) => {
      const focusWasInside = sidebarRef.current?.contains(document.activeElement);
      setMobile(event.matches);
      setPeek(false);
      clearTimeout(hoverClose.current);
      setOpen(false);
      if (focusWasInside || document.activeElement === menuButtonRef.current) {
        requestAnimationFrame(() => (event.matches ? menuButtonRef : collapseButtonRef).current?.focus());
      }
    };
    query.addEventListener("change", update);
    return () => query.removeEventListener("change", update);
  }, []);

  useEffect(() => {
    let active = true;
    workspaceApi.listTasks({ page: 1, page_size: 5 }).then((page) => { if (active) setRecent(page.items); }).catch(() => undefined);
    return () => { active = false; };
  }, []);

  useEffect(() => {
    if (!mobile || !open) return;
    firstDrawerLinkRef.current?.focus();
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    const handleKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") { event.preventDefault(); closeDrawer(); return; }
      if (event.key !== "Tab") return;
      const focusable = [...(sidebarRef.current?.querySelectorAll<HTMLElement>('a[href], button:not(:disabled), [tabindex="0"]') || [])];
      const first = focusable[0];
      const last = focusable.at(-1);
      if (!first || !last) return;
      if (!sidebarRef.current?.contains(document.activeElement)) { event.preventDefault(); (event.shiftKey ? last : first).focus(); }
      else if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus(); }
      else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); }
    };
    window.addEventListener("keydown", handleKey);
    return () => { document.body.style.overflow = previousOverflow; window.removeEventListener("keydown", handleKey); };
  }, [closeDrawer, mobile, open]);

  const closeOnInternalNavigation = (event: React.MouseEvent<HTMLElement>) => {
    const link = event.target instanceof Element ? event.target.closest<HTMLAnchorElement>("a[href]") : null;
    if (link && !event.metaKey && !event.ctrlKey && !event.shiftKey && !event.altKey && new URL(link.href).origin === window.location.origin) {
      closeDrawer();
      if (rail) { setPeek(false); requestAnimationFrame(() => collapseButtonRef.current?.focus()); }
    }
  };

  return (
    <div className={`workspace-shell${rail ? " is-collapsed" : ""}`}>
      {rail && <div className="workspace-collapsed-header" onPointerEnter={keepPeek} onPointerLeave={hidePeekSoon}>
        <button ref={collapseButtonRef} className="workspace-collapse" type="button" aria-label={wt("sidebarExpand")} title={wt("sidebarExpand")} aria-expanded={peek} aria-controls="workspace-sidebar" onPointerEnter={event => { if (event.pointerType === "mouse") { keepPeek(); setPeek(true); } }} onClick={togglePinned} onKeyDown={event => { if (event.key === "ArrowDown") { event.preventDefault(); setPeek(true); requestAnimationFrame(() => firstDrawerLinkRef.current?.focus()); } }}><Icon name={peek ? "expand" : "menu"}/></button>
        <Brand/>
      </div>}
      {mobile && <div className="workspace-mobile-header" inert={open ? true : undefined}>
        <button ref={menuButtonRef} className="workspace-menu-button" type="button" onClick={() => setOpen(true)} aria-label={wt("menuOpen")} aria-expanded={open} aria-controls="workspace-sidebar"><Icon name="menu"/></button>
        <Brand/>
      </div>}
      {mobile && open && <button className="workspace-scrim" type="button" tabIndex={-1} aria-hidden="true" onClick={closeDrawer}/>}
      <aside ref={sidebarRef} id="workspace-sidebar" className={`workspace-sidebar${open ? " is-open" : ""}${rail ? " is-floating" : ""}`} hidden={rail && !peek} inert={(mobile && !open) || (rail && !peek) ? true : undefined} aria-hidden={(mobile && !open) || (rail && !peek) ? true : undefined} role={mobile && open ? "dialog" : undefined} aria-modal={mobile && open ? true : undefined} aria-label={mobile && open ? wt("workspaceNav") : undefined} onClick={closeOnInternalNavigation} onPointerEnter={keepPeek} onPointerLeave={rail ? hidePeekSoon : undefined} onBlur={event => { if (rail && !event.currentTarget.contains(event.relatedTarget) && event.relatedTarget !== collapseButtonRef.current) setPeek(false); }}>
        {!rail && <div className="workspace-brand"><Brand/>{mobile ? <button className="workspace-drawer-close" type="button" aria-label={wt("menuClose")} onClick={closeDrawer}><Icon name="x" size={18}/></button> : <button ref={collapseButtonRef} className="workspace-collapse" type="button" aria-label={wt("sidebarCollapse")} title={wt("sidebarCollapse")} aria-expanded="true" aria-controls="workspace-sidebar" onClick={togglePinned}><Icon name="collapse" size={18}/></button>}</div>}
        <nav className="workspace-nav" aria-label={wt("workspaceNav")}>
          <NavLink ref={firstDrawerLinkRef} className="workspace-create" to="/workspace/new" aria-label={wt("createTask")} title={rail ? wt("createTask") : undefined}><Icon name="plus"/><span>{wt("createTask")}</span></NavLink>
          <NavLink to="/workspace/tasks" aria-label={wt("tasks")} title={rail ? wt("tasks") : undefined}><Icon name="layers"/><span>{wt("tasks")}</span></NavLink>
        </nav>
        <section className="workspace-recent" aria-labelledby="recent-heading">
          <h2 id="recent-heading">{wt("recent")}</h2>
          {recent.length ? recent.map((item) => <Link key={item.id} to={`/workspace/tasks/${item.id}`} title={item.title} aria-label={item.title} aria-describedby={`recent-status-${item.id}`}><StatusChip id={`recent-status-${item.id}`} status={item.status} stageMessage={item.stage_message} compact/><span>{item.title}</span></Link>) : <p>{wt("noRecent")}</p>}
        </section>
        <div className="workspace-sidebar-bottom">
          <Link to="/workspace/settings" className="workspace-account" aria-label={`${wt("account")}${wt("labelSeparator")}${user?.username || ""}`} title={user?.username}><span className="workspace-avatar"><Icon name="user" size={18}/></span></Link>
          <div className="workspace-utility-row">
            <a href={GITHUB_URL} target="_blank" rel="noreferrer" aria-label={wt("github")} title={wt("github")}><Icon name="github" size={18}/></a>
            <a href="/api/docs" aria-label={wt("api")} title={wt("api")}><Icon name="code" size={18}/></a>
            <Link to="/workspace/settings" aria-label={wt("settings")} title={wt("settings")}><Icon name="settings" size={18}/></Link>
          </div>
        </div>
      </aside>
      <main className="workspace-main" inert={mobile && open ? true : undefined}><Outlet/></main>
    </div>
  );
}
