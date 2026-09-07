import { Icon } from "./Icon";
import { Link, Navigate, Outlet, useLocation } from "react-router-dom";
import { useAuth } from "../providers/AuthProvider";
import { useLocale } from "../providers/LocaleProvider";

import { isAdmin } from "../lib/adminRole";

export function RouteGuard({ role = "user" }: { role?: "admin" | "user" }) {
  const { authError, checking, refresh, user } = useAuth();
  const { t, locale } = useLocale();
  const location = useLocation();
  if (checking) return <div className="route-loading" role="status"><Icon name="refresh" size={24} spin/><span className="sr-only">{t("authChecking")}</span></div>;
  if (authError) {
    return <main className="route-state"><section className="route-error" role="alert"><h1>{t("authCheckFailed")}</h1><p>{t("authCheckFailedBody")}</p><button className="button button-primary button-icon" type="button" aria-label={t("retry")} title={t("retry")} onClick={() => void refresh()}><Icon name="refresh"/></button></section></main>;
  }
  if (!user) {
    const next = `${location.pathname}${location.search}${location.hash}`;
    return <Navigate to={`/login?${new URLSearchParams({ next })}`} replace />;
  }
  if (role === "user" && isAdmin(user)) return <Navigate to="/admin" replace/>;
  if (role === "admin" && !isAdmin(user)) return <main className="route-state"><section className="route-error" role="alert"><Icon name="ban" size={28}/><h1>{locale === "zh" ? "需要管理员权限" : "Administrator access required"}</h1><p>{locale === "zh" ? "当前账户无法访问管理控制台。" : "This account cannot access administration."}</p><Link className="button button-primary" to="/workspace/new">{locale === "zh" ? "返回工作台" : "Back to workspace"}</Link></section></main>;
  return <Outlet />;
}
