import { useEffect, useRef, useState } from "react";
import { Link, NavLink, useLocation } from "react-router-dom";
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
  const { pathname } = useLocation();
  const [menuOpen, setMenuOpen] = useState(false);
  const menuToggle = useRef<HTMLButtonElement>(null);
  const navigation = useRef<HTMLElement>(null);
  useEffect(() => { setMenuOpen(false); }, [pathname]);
  useEffect(() => {
    if (!menuOpen) return;
    navigation.current?.querySelector<HTMLAnchorElement>("a[href]")?.focus();
    const close = (event: KeyboardEvent) => {
      if (event.key === "Escape") { setMenuOpen(false); menuToggle.current?.focus(); }
    };
    document.addEventListener("keydown", close);
    return () => document.removeEventListener("keydown", close);
  }, [menuOpen]);
  return (
    <header className={`public-header${menuOpen ? " menu-open" : ""}`}>
      <div className="header-inner">
        <Brand />
        <nav ref={navigation} id="public-navigation" className="public-nav" aria-label={t("mainNav")}>
          <NavLink to="/" end>{t("home")}</NavLink>
          <NavLink to="/api/docs">{t("api")}</NavLink>
        </nav>
        <div className="header-actions">
          <button className="icon-button theme-button" type="button" onClick={toggleTheme} aria-label={theme === "dark" ? t("themeLight") : t("themeDark")} title={theme === "dark" ? t("themeLight") : t("themeDark")}>
            <Icon name={theme === "dark" ? "sun" : "moon"}/>
          </button>
          <button className="text-button language-button" type="button" onClick={toggleLocale} aria-label={t("language")}><Icon name="language"/><span>{t("language")}</span></button>
          <a className="icon-button github-button" href={GITHUB_URL} target="_blank" rel="noreferrer" aria-label={t("github")} title={t("github")}><Icon name="github"/></a>
          <Link className="button button-outline header-cta" to="/workspace/new">{t("onlineUse")}</Link>
          {user ? <Link className="account-link" to="/workspace/settings" aria-label={user.username}><Icon name="user"/><span>{user.username}</span></Link> : <Link className="login-link" to="/login" aria-label={t("login")}><Icon name="user"/><span>{t("login")}</span></Link>}
          <button ref={menuToggle} className="icon-button public-menu-toggle" type="button" aria-label={t(menuOpen ? "menuClose" : "menuOpen")} aria-controls="public-navigation" aria-expanded={menuOpen} onClick={() => setMenuOpen(!menuOpen)}><span aria-hidden="true">{menuOpen ? "×" : "☰"}</span></button>
        </div>
      </div>
    </header>
  );
}
