import { Link } from "react-router-dom";
import { useLocale } from "../providers/LocaleProvider";

export function BrandMark({ size = 38, label }: { size?: number; label?: string }) {
  return <img src="/assets/brand/dashanbing-mark.svg" alt={label || ""} aria-label={label} aria-hidden={label ? undefined : true} className="brand-symbol" width={size} height={size}/>;
}

export function Brand() {
  const { t } = useLocale();
  return <Link className="brand" to="/" aria-label={t("brandHome")}><BrandMark label={t("brandMark")}/><span className="brand-name"><strong>{t("brandPrimary")}</strong><small>{t("brandSecondary")}</small></span></Link>;
}
