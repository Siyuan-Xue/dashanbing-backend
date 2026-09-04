import { PublicHeader } from "../components/PublicHeader";
import { useLocale } from "../providers/LocaleProvider";

export function ProtectedRouteScaffold() {
  const { t } = useLocale();
  return <div className="reserved-site"><PublicHeader/><main className="reserved-route section-shell"><span className="reserved-pulse"/><h1>{t("routePreparing")}</h1><p>{t("routePreparingBody")}</p></main></div>;
}
