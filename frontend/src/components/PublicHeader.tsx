import { useEffect, useRef, useState } from "react";
import { Link, NavLink, useLocation, useNavigate } from "react-router-dom";
import { Brand } from "./Brand";
import { Icon } from "./Icon";
import { useAuth } from "../providers/AuthProvider";
import { useLocale } from "../providers/LocaleProvider";
import { useTheme } from "../providers/ThemeProvider";

const GITHUB_URL = "https://github.com/Siyuan-Xue/dashanbing-backend";

export function PublicHeader() {
  const { user, logout } = useAuth();
  const { t, toggleLocale } = useLocale();
  const { theme, toggleTheme } = useTheme();
  const location = useLocation();
  const navigate = useNavigate();
  const [menuOpen, setMenuOpen] = useState(false);
  const [accountOpen, setAccountOpen] = useState(false);
  const [loggingOut, setLoggingOut] = useState(false);
  const [logoutFailed, setLogoutFailed] = useState(false);
  const account = useRef<HTMLDivElement>(null);
  const accountToggle = useRef<HTMLButtonElement>(null);
  const logoutButton = useRef<HTMLButtonElement>(null);
  const loginLink = useRef<HTMLAnchorElement>(null);
  const menuToggle = useRef<HTMLButtonElement>(null);
  const navigation = useRef<HTMLElement>(null);
  useEffect(() => { setMenuOpen(false); setAccountOpen(false); }, [location.key]);
  useEffect(() => {
    if (!user && location.state?.focusLogin) {
      if (loginLink.current?.getClientRects().length) loginLink.current.focus();
      else menuToggle.current?.focus();
      navigate("/", { replace: true, state: null });
    }
  }, [user, location.state, navigate]);
  useEffect(() => {
    if (!accountOpen) return;
    logoutButton.current?.focus();
    const closeOutside = (event: Event) => {
      if (event.target instanceof Node && !account.current?.contains(event.target)) setAccountOpen(false);
    };
    document.addEventListener("pointerdown", closeOutside);
    document.addEventListener("focusin", closeOutside);
    return () => {
      document.removeEventListener("pointerdown", closeOutside);
      document.removeEventListener("focusin", closeOutside);
    };
  }, [accountOpen]);
  const signOut = async () => {
    if (loggingOut) return;
    setLoggingOut(true);
    setLogoutFailed(false);
    try {
      await logout();
      setAccountOpen(false);
      setMenuOpen(false);
    } catch {
      setLogoutFailed(true);
    } finally {
      setLoggingOut(false);
    }
  };
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
          {user ? (
            <div ref={account} className="account-menu" onKeyDown={event => {
              if (event.key === "Escape" && accountOpen) {
                event.stopPropagation();
                setAccountOpen(false);
                accountToggle.current?.focus();
              }
            }}>
              <button ref={accountToggle} className="account-link" type="button" aria-label={`${t("account")}：${user.username}`} aria-expanded={accountOpen} aria-controls="account-dropdown" onClick={() => { setAccountOpen(!accountOpen); setLogoutFailed(false); }}>
                <Icon name="user"/>
              </button>
              {accountOpen && (
                <section id="account-dropdown" className="account-dropdown" aria-label={t("account")} aria-busy={loggingOut}>
                  <div className="account-info">
                    <strong>{user.username}</strong>
                    {user.email && <span>{user.email}</span>}
                  </div>
                  <button ref={logoutButton} className="account-logout" type="button" aria-disabled={loggingOut} onClick={() => void signOut()}>
                    <Icon name="logout"/><span>{t(loggingOut ? "loggingOut" : "logout")}</span>
                  </button>
                  {logoutFailed && <p className="account-error" role="alert">{t("logoutFailed")}</p>}
                </section>
              )}
            </div>
          ) : <Link ref={loginLink} className="login-link" to="/login" aria-label={t("login")}><Icon name="user"/><span>{t("login")}</span></Link>}
          <button ref={menuToggle} className="icon-button public-menu-toggle" type="button" aria-label={t(menuOpen ? "menuClose" : "menuOpen")} aria-controls="public-navigation" aria-expanded={menuOpen} onClick={() => { setAccountOpen(false); setMenuOpen(!menuOpen); }}><span aria-hidden="true">{menuOpen ? "×" : "☰"}</span></button>
        </div>
      </div>
    </header>
  );
}
