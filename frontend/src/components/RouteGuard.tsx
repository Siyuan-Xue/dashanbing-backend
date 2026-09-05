import { Icon } from "./Icon";
import { Navigate, Outlet, useLocation } from "react-router-dom";
import { useAuth } from "../providers/AuthProvider";
import { useLocale } from "../providers/LocaleProvider";

export function RouteGuard() {
  const { authError, checking, refresh, user } = useAuth();
  const { t } = useLocale();
  const location = useLocation();
  if (checking) return <div className="route-loading" role="status"><span aria-hidden="true"/><span className="sr-only">{t("authChecking")}</span></div>;
  if (authError) {
    return <main className="route-state"><section className="route-error" role="alert"><h1>{t("authCheckFailed")}</h1><p>{t("authCheckFailedBody")}</p><button className="button button-primary button-icon" type="button" aria-label={t("retry")} title={t("retry")} onClick={() => void refresh()}><Icon name="refresh"/></button></section></main>;
  }
  if (!user) {
    const next = `${location.pathname}${location.search}`;
    return <Navigate to={`/login?${new URLSearchParams({ next })}`} replace />;
  }
  return <Outlet />;
}
