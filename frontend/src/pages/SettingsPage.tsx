import { Icon } from "../components/Icon";
import { WorkspaceState } from "../components/WorkspaceState";
import { useLocale } from "../providers/LocaleProvider";
import { useTheme } from "../providers/ThemeProvider";
import { workspaceApi } from "../workspace/api";
import { useLoadable } from "../workspace/useLoadable";
import { useWorkspaceCopy } from "../workspace/useWorkspaceCopy";

export function SettingsPage() {
  const wt = useWorkspaceCopy();
  const { locale, toggleLocale } = useLocale();
  const { theme, toggleTheme } = useTheme();
  const { value: usage, error, reload } = useLoadable(workspaceApi.usage);
  const quotaCards = usage ? [
    [wt("submittedToday"), usage.submitted_today], [wt("unfinished"), usage.unfinished_tasks], [wt("drafts"), usage.drafts], [wt("apiKeys"), usage.active_api_keys],
  ] as const : [];
  return <div className="workspace-page settings-page">
    <header className="workspace-page-header"><div><span className="page-eyebrow">ACCOUNT</span><h1>{wt("settings")}</h1><p>{wt("settingsBody")}</p></div></header>
    {error ? <WorkspaceState title={wt("loadFailed")} body={error.message} onRetry={reload}/> : !usage ? <div className="loading-block" role="status"/> : <>
      <section className="settings-section"><div className="settings-heading"><span><Icon name="chart"/></span><div><h2>{wt("usage")}</h2><p>Beta</p></div></div><div className="quota-grid">{quotaCards.map(([label, value]) => <article key={label}><span>{label}</span><b>{value.used} / {value.limit}</b><div><i style={{ width: `${Math.min(100, value.used / value.limit * 100)}%` }}/></div></article>)}</div></section>
      <section className="settings-section"><div className="settings-heading"><span><Icon name="clock"/></span><div><h2>{wt("retention")}</h2><p>UTC</p></div></div><dl className="retention-grid"><div><dt>{wt("drafts")}</dt><dd>{usage.retention.drafts}</dd></div><div><dt>{wt("enrollment")}</dt><dd>{usage.retention.enrollment_data}</dd></div><div><dt>{wt("rawInputs")}</dt><dd>{usage.retention.raw_inputs}</dd></div><div><dt>{wt("results")}</dt><dd>{usage.retention.results}</dd></div></dl></section>
    </>}
    <section className="settings-section"><div className="settings-heading"><span><Icon name="settings"/></span><div><h2>{wt("preferences")}</h2><p>Local</p></div></div><div className="preference-rows"><div><span><b>{wt("language")}</b><small>{locale === "zh" ? "简体中文" : "English"}</small></span><button className="button button-outline" type="button" onClick={toggleLocale}>{locale === "zh" ? "English" : "中文"}</button></div><div><span><b>{wt("theme")}</b><small>{theme === "dark" ? "Dark" : "Light"}</small></span><button className="button button-outline" type="button" onClick={toggleTheme} aria-label={theme === "dark" ? (locale === "zh" ? "切换到浅色主题" : "Switch to light theme") : (locale === "zh" ? "切换到深色主题" : "Switch to dark theme")}>{theme === "dark" ? <Icon name="sun"/> : <Icon name="moon"/>}{theme === "dark" ? "Light" : "Dark"}</button></div></div></section>
  </div>;
}
