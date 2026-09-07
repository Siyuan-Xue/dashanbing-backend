import { useState } from "react";
import { useAuth } from "../providers/AuthProvider";
import { useLocale } from "../providers/LocaleProvider";
import { useTheme } from "../providers/ThemeProvider";
import { useAdminCopy } from "../lib/adminCopy";
import { Icon } from "./Icon";

export function AdminAccountMenu() {
  const { user, logout } = useAuth();
  const { t, toggleLocale } = useLocale();
  const { theme, toggleTheme } = useTheme();
  const at = useAdminCopy();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(false);
  async function signOut() { if (busy) return; setBusy(true); setError(false); try { await logout(); } catch { setError(true); } finally { setBusy(false); } }
  return <section aria-label={t("account")} className="admin-account">
    <div className="admin-account-identity"><Icon name="user"/><span><strong>{user?.username}</strong><small>{at("administrator")}</small></span></div>
    <div className="admin-actions">
      <button className="table-action" type="button" onClick={toggleTheme} aria-label={t(theme === "dark" ? "themeLight" : "themeDark")} title={t(theme === "dark" ? "themeLight" : "themeDark")}><Icon name={theme === "dark" ? "sun" : "moon"}/></button>
      <button className="table-action" type="button" onClick={toggleLocale} aria-label={t("language")} title={t("language")}><Icon name="language"/></button>
      <button className="table-action admin-danger" type="button" disabled={busy} onClick={() => void signOut()} aria-label={t(busy ? "loggingOut" : "logout")} title={t("logout")}><Icon name="logout"/></button>
    </div>
    {error && <p role="alert">{t("logoutFailed")}</p>}
  </section>;
}
