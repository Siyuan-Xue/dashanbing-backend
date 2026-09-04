import { Link } from "react-router-dom";
import { useLocale } from "../providers/LocaleProvider";

export function BrandMark({ size = 38, label }: { size?: number; label?: string }) {
  return (
    <svg aria-label={label} aria-hidden={label ? undefined : true} className="brand-symbol" width={size} height={size} viewBox="0 0 48 48" role={label ? "img" : undefined}>
      <rect width="48" height="48" rx="15" fill="currentColor" />
      <path d="M7 27 17.5 11l5.2 7.3L27.8 9 41 27H7Z" fill="#f7f9ff" />
      <path d="m7 27 6.2 12h21.6L41 27H7Z" fill="#72d8f3" />
      <path d="M10 27h28" stroke="#a9edff" strokeWidth="1.6" />
      <path d="M24 27a11 11 0 0 0 9.7 10.9A10.9 10.9 0 0 0 38 29v-2H24Z" fill="#ff7a45" />
      <path d="M28.5 28.3c1.4 4.5 4.4 7 8 7.6M25.5 33.7c3.6-1.7 7.4-2.1 11.4-1.3" fill="none" stroke="#fff" strokeWidth="1.25" strokeLinecap="round" />
    </svg>
  );
}

export function Brand() {
  const { t } = useLocale();
  return <Link className="brand" to="/" aria-label={t("brandHome")}><BrandMark label={t("brandMark")}/><span className="brand-name"><strong>{t("brandPrimary")}</strong><small>{t("brandSecondary")}</small></span></Link>;
}
