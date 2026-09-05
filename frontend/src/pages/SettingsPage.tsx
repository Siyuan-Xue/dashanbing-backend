import { useState } from "react";
import { useAuth } from "../providers/AuthProvider";
import { Icon } from "../components/Icon";
import { WorkspaceState } from "../components/WorkspaceState";
import { formatRetentionDuration } from "../localization";
import { useLocale } from "../providers/LocaleProvider";
import { useTheme } from "../providers/ThemeProvider";
import { workspaceApi } from "../workspace/api";
import { useLoadable } from "../workspace/useLoadable";
import { useWorkspaceCopy } from "../workspace/useWorkspaceCopy";

export function SettingsPage() {
  const wt = useWorkspaceCopy();
  const { locale, toggleLocale, t } = useLocale();
  const { logout } = useAuth();
  const [loggingOut, setLoggingOut] = useState(false);
  const [logoutFailed, setLogoutFailed] = useState(false);
  const signOut = async () => {
    if (loggingOut) return;
    setLoggingOut(true);
    setLogoutFailed(false);
    try {
      await logout();
    } catch {
      setLogoutFailed(true);
    } finally {
      setLoggingOut(false);
    }
  };
  const { theme, toggleTheme } = useTheme();
  const { value: usage, error, reload } = useLoadable(workspaceApi.usage);
  const quotaCards = usage ? [
    [wt("submittedToday"), usage.submitted_today], [wt("unfinished"), usage.unfinished_tasks], [wt("drafts"), usage.drafts], [wt("apiKeys"), usage.active_api_keys],
  ] as const : [];
  return <div className="workspace-page settings-page">
    <header className="workspace-page-header"><div><h1>{wt("settings")}</h1></div><button className="button button-outline settings-logout" type="button" aria-disabled={loggingOut} onClick={() => void signOut()}><Icon name="logout" size={18}/>{t(loggingOut ? "loggingOut" : "logout")}</button></header>
      {logoutFailed && <p className="settings-logout-error" role="alert">{t("logoutFailed")}</p>}
      <div className="settings-content">
        <section id="usage" className="settings-section" aria-labelledby="usage-heading">
          <h2 id="usage-heading">{wt("usage")}</h2>
          {error ? <WorkspaceState title={wt("loadFailed")} body={error.message} onRetry={reload}/> : !usage ? <div className="loading-block" role="status" aria-label={wt("usage")}/> : <div className="quota-grid">{quotaCards.map(([label, value]) => <article key={label}><span>{label}</span><b>{value.used} / {value.limit}</b><div><i style={{ width: `${value.limit > 0 ? Math.min(100, value.used / value.limit * 100) : 0}%` }}/></div></article>)}</div>}
        </section>
        <section id="retention" className="settings-section" aria-labelledby="retention-heading">
          <h2 id="retention-heading">{wt("retention")}</h2>
          {usage ? <dl className="retention-grid"><div><dt>{wt("drafts")}</dt><dd>{formatRetentionDuration(locale, usage.retention.drafts)}</dd></div><div><dt>{wt("enrollment")}</dt><dd>{formatRetentionDuration(locale, usage.retention.enrollment_data)}</dd></div><div><dt>{wt("rawInputs")}</dt><dd>{formatRetentionDuration(locale, usage.retention.raw_inputs)}</dd></div><div><dt>{wt("results")}</dt><dd>{formatRetentionDuration(locale, usage.retention.results)}</dd></div></dl> : <p className="settings-note">{error ? wt("loadFailed") : wt("resultLoading")}</p>}
        </section>
        <section id="preferences" className="settings-section" aria-labelledby="preferences-heading">
          <h2 id="preferences-heading">{wt("preferences")}</h2>
          <div className="preference-rows"><div><span><b>{wt("language")}</b><small>{locale === "zh" ? "简体中文" : "English"}</small></span><button className="button button-outline" type="button" onClick={toggleLocale}>{locale === "zh" ? "English" : "中文"}</button></div><div><span><b>{wt("theme")}</b><small>{wt(theme === "dark" ? "dark" : "light")}</small></span><button className="button button-outline" type="button" onClick={toggleTheme} aria-label={theme === "dark" ? (locale === "zh" ? "切换到浅色主题" : "Switch to light theme") : (locale === "zh" ? "切换到深色主题" : "Switch to dark theme")}>{theme === "dark" ? <Icon name="sun" size={18}/> : <Icon name="moon" size={18}/>}{wt(theme === "dark" ? "light" : "dark")}</button></div></div>
        </section>
      </div>
  </div>;
}
