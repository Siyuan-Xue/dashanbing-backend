import { useCallback, useEffect, useRef, useState } from "react";
import { NavLink, Outlet, useLocation } from "react-router-dom";

import { useAdminCopy } from "../lib/adminCopy";
import { AdminAccountMenu } from "./AdminAccountMenu";
import "../styles/admin.css";
import { Brand } from "./Brand";
import { Icon } from "./Icon";

const MOBILE_QUERY = "(max-width: 767px)";

export function AdminShell() {
  const wt = useAdminCopy();
  const location = useLocation();
  const [peek, setPeek] = useState(false);
  const hoverClose = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);
  const [open, setOpen] = useState(false);
  const [mobile, setMobile] = useState(() => window.matchMedia(MOBILE_QUERY).matches);
  const [collapsed, setCollapsed] = useState(() => window.matchMedia("(min-width: 768px) and (max-width: 1279px)").matches);
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
    <div className={`workspace-shell admin-shell${rail ? " is-collapsed" : ""}`}>
      {rail && <div className="workspace-collapsed-header" onPointerEnter={keepPeek} onPointerLeave={hidePeekSoon}>
        <button ref={collapseButtonRef} className="workspace-collapse" type="button" aria-label={wt("expand")} title={wt("expand")} aria-expanded={peek} aria-controls="admin-sidebar" onPointerEnter={event => { if (event.pointerType === "mouse") { keepPeek(); setPeek(true); } }} onClick={togglePinned} onKeyDown={event => { if (event.key === "ArrowDown") { event.preventDefault(); setPeek(true); requestAnimationFrame(() => firstDrawerLinkRef.current?.focus()); } }}><Icon name={peek ? "expand" : "menu"}/></button>
        <Brand/>
      </div>}
      {mobile && <div className="workspace-mobile-header" inert={open ? true : undefined}>
        <button ref={menuButtonRef} className="workspace-menu-button" type="button" onClick={() => setOpen(true)} aria-label={wt("menuOpen")} aria-expanded={open} aria-controls="admin-sidebar"><Icon name="menu"/></button>
        <Brand/>
      </div>}
      {mobile && open && <button className="workspace-scrim" type="button" tabIndex={-1} aria-hidden="true" onClick={closeDrawer}/>}
      <aside ref={sidebarRef} id="admin-sidebar" className={`workspace-sidebar${open ? " is-open" : ""}${rail ? " is-floating" : ""}`} hidden={rail && !peek} inert={(mobile && !open) || (rail && !peek) ? true : undefined} aria-hidden={(mobile && !open) || (rail && !peek) ? true : undefined} role={mobile && open ? "dialog" : undefined} aria-modal={mobile && open ? true : undefined} aria-label={mobile && open ? wt("navigation") : undefined} onClick={closeOnInternalNavigation} onPointerEnter={keepPeek} onPointerLeave={rail ? hidePeekSoon : undefined} onBlur={event => { if (rail && !event.currentTarget.contains(event.relatedTarget) && event.relatedTarget !== collapseButtonRef.current) setPeek(false); }}>
        {!rail && <div className="workspace-brand"><Brand/>{mobile ? <button className="workspace-drawer-close" type="button" aria-label={wt("menuClose")} onClick={closeDrawer}><Icon name="x" size={18}/></button> : <button ref={collapseButtonRef} className="workspace-collapse" type="button" aria-label={wt("collapse")} title={wt("collapse")} aria-expanded="true" aria-controls="admin-sidebar" onClick={togglePinned}><Icon name="collapse" size={18}/></button>}</div>}
        <nav className="workspace-nav admin-nav" aria-label={wt("navigation")}>
          {([ ["overview", "chart"], ["users", "team"], ["scheduling", "layers"], ["quotas", "settings"], ["operations", "activity"], ["audit", "file"] ] as const).map(([section, icon], index) => <NavLink ref={index === 0 ? firstDrawerLinkRef : undefined} key={section} to={`/admin/${section}`} aria-label={wt(section)}><Icon name={icon}/><span>{wt(section)}</span></NavLink>)}
        </nav>
        <div className="admin-sidebar-bottom"><AdminAccountMenu/></div>
      </aside>
      <main className="workspace-main" inert={mobile && open ? true : undefined}><Outlet/></main>
    </div>
  );
}
