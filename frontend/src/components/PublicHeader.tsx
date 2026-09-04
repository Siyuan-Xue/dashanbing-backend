import { Link, NavLink } from "react-router-dom";
import { Brand } from "./Brand";
import { Icon } from "./Icon";
import { useAuth } from "../providers/AuthProvider";
import { useLocale } from "../providers/LocaleProvider";
import { useTheme } from "../providers/ThemeProvider";

const GITHUB_URL = "https://github.com/Siyuan-Xue/dashanbing-backend";

export function PublicHeader() {
  const { user } = useAuth();
  const { t, toggleLocale } = useLocale();
  const { theme, toggleTheme } = useTheme();
  return (
    <header className="public-header">
      <div className="header-inner">
        <Brand />
        <nav className="public-nav" aria-label="主导航">
          <NavLink to="/" end>{t("home")}</NavLink>
          <Link to="/api/docs">{t("api")}</Link>
        </nav>
        <div className="header-actions">
          <button className="icon-button" type="button" onClick={toggleTheme} aria-label={theme === "dark" ? t("themeLight") : t("themeDark")} title={theme === "dark" ? t("themeLight") : t("themeDark")}>
            <Icon name={theme === "dark" ? "sun" : "moon"}/>
          </button>
          <button className="text-button language-button" type="button" onClick={toggleLocale} aria-label={t("language")}><Icon name="language"/><span>{t("language")}</span></button>
          <a className="icon-button github-button" href={GITHUB_URL} target="_blank" rel="noreferrer" aria-label={t("github")} title={t("github")}><Icon name="github"/></a>
          <Link className="button button-outline header-cta" to="/workspace/new">{t("onlineUse")}</Link>
          {user ? <Link className="account-link" to="/workspace/settings"><Icon name="user"/><span>{user.username}</span></Link> : <Link className="login-link" to="/login"><Icon name="user"/><span>{t("login")}</span></Link>}
        </div>
      </div>
    </header>
  );
}
