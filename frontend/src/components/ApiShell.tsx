import { useEffect, useRef, useState } from "react";
import { NavLink, Outlet } from "react-router-dom";
import { PublicHeader } from "./PublicHeader";
import { Icon } from "./Icon";
import { useLocale } from "../providers/LocaleProvider";
import { apiCopy } from "../apiCenter/copy";

export function ApiShell() {
  const { locale } = useLocale();
  const c = apiCopy[locale];
  const [open, setOpen] = useState(false);
  const closeRef = useRef<HTMLButtonElement>(null);
  const drawerRef = useRef<HTMLElement>(null);
  const menuRef = useRef<HTMLButtonElement>(null);
  const closeMenu = () => {
    setOpen(false);
    requestAnimationFrame(() => menuRef.current?.focus());
  };
  useEffect(() => {
    if (!open) return;
    closeRef.current?.focus();
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") { event.preventDefault(); closeMenu(); return; }
      if (event.key !== "Tab" || !drawerRef.current) return;
      const focusable = [...drawerRef.current.querySelectorAll<HTMLElement>("button:not(:disabled), a[href]")];
      if (!focusable.length) return;
      const first = focusable[0];
      const last = focusable.at(-1)!;
      if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus(); }
      if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open]);
  return <div className="public-site api-site">
    <PublicHeader/>
    <button ref={menuRef} className="api-mobile-menu" type="button" aria-label={c.menu} aria-expanded={open} onClick={() => setOpen(true)}><Icon name="menu"/>{c.docs}</button>
    {open && <button className="api-scrim" type="button" aria-label={c.close} onClick={closeMenu}/>}
    <div className="api-layout">
      <aside ref={drawerRef} className={`api-sidebar${open ? " open" : ""}`} aria-label={c.nav}>
        <button ref={closeRef} className="api-sidebar-close" type="button" aria-label={c.close} onClick={closeMenu}><Icon name="x"/></button>
        <p><Icon name="code"/>DaShanBing API</p>
        <nav aria-label={c.nav}>
          <NavLink to="/api/docs" onClick={closeMenu}><Icon name="file"/>{c.docs}</NavLink>
          <NavLink to="/api/keys" onClick={closeMenu}><Icon name="settings"/>{c.keys}</NavLink>
        </nav>
      </aside>
      <Outlet/>
    </div>
  </div>;
}
