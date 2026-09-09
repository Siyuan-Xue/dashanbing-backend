import { useEffect, useRef, useState } from "react";
import { useLocation } from "react-router-dom";
import { useAuth } from "../providers/AuthProvider";
import { useLocale } from "../providers/LocaleProvider";
import { useTheme } from "../providers/ThemeProvider";
import { useAdminCopy } from "../lib/adminCopy";
import { Icon } from "./Icon";
import { WorkspaceSidebarFooter } from "./WorkspaceSidebarFooter";

export function AdminAccountMenu() {
  const { user, logout } = useAuth();
  const { t, toggleLocale } = useLocale();
  const { theme, toggleTheme } = useTheme();
  const at = useAdminCopy();
  const location = useLocation();
  const [open, setOpen] = useState(false);
  const root = useRef<HTMLDivElement>(null);
  const trigger = useRef<HTMLButtonElement | null>(null);
  const panel = useRef<HTMLElement>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(false);
  useEffect(() => setOpen(false), [location.key]);
  useEffect(() => {
    if (!open) return;
    panel.current?.focus({ preventScroll: true });
    const outside = (event: PointerEvent) => { if (!root.current?.contains(event.target as Node)) setOpen(false); };
    document.addEventListener("pointerdown", outside);
    return () => document.removeEventListener("pointerdown", outside);
  }, [open]);
  const toggle = (button: HTMLButtonElement) => { trigger.current = button; setOpen(value => !value); setError(false); };
  async function signOut() { if (busy) return; setBusy(true); setError(false); try { await logout(); } catch { setError(true); } finally { setBusy(false); } }
  return <div ref={root} className="workspace-account-menu" onBlur={event => {
    if (event.relatedTarget && !event.currentTarget.contains(event.relatedTarget)) setOpen(false);
  }} onKeyDown={event => {
    if (open && event.key === "Escape") { event.preventDefault(); event.stopPropagation(); setOpen(false); trigger.current?.focus(); }
  }}>
    {open && <section ref={panel} id="admin-account-options" className="workspace-account-popover" aria-label={t("account")} tabIndex={-1}>
      <div className="workspace-account-info"><strong>{user?.username}</strong><span>{at("administrator")}</span>{user?.email && <small>{user.email}</small>}</div>
    </section>}
    {error && <p className="workspace-account-error" role="alert">{t("logoutFailed")}</p>}
    <WorkspaceSidebarFooter
      account={<button className="workspace-account workspace-account-named" type="button" aria-label={`${t("account")}：${user?.username || ""}`} title={user?.username} aria-expanded={open} aria-controls="admin-account-options" onClick={event => toggle(event.currentTarget)}><span className="workspace-avatar"><Icon name="user" size={18}/></span><span className="workspace-account-name">{user?.username}</span></button>}
      tools={<>
        <button type="button" onClick={toggleTheme} aria-label={t(theme === "dark" ? "themeLight" : "themeDark")} title={t(theme === "dark" ? "themeLight" : "themeDark")}><Icon name={theme === "dark" ? "sun" : "moon"} size={18}/></button>
        <button type="button" onClick={toggleLocale} aria-label={t("language")} title={t("language")}><Icon name="language" size={18}/></button>
        <button className="workspace-logout" type="button" disabled={busy} onClick={() => void signOut()} aria-label={t(busy ? "loggingOut" : "logout")} title={t("logout")}><Icon name="logout" size={18}/></button>
      </>}
    />
  </div>;
}
