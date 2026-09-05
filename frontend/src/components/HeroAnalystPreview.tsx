import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { Icon } from "./Icon";
import { useLocale } from "../providers/LocaleProvider";
import { useTheme } from "../providers/ThemeProvider";
import { useAnalystCopy } from "../analyst/copy";
import { parsePreviewManifest } from "../analyst/previewManifest";
import type { PreviewManifest } from "../analyst/previewManifest";

export function HeroAnalystPreview({ decorative = false }: { decorative?: boolean }) {
  const { locale, t: publicCopy } = useLocale(); const { theme } = useTheme(); const t = useAnalystCopy();
  const [manifest, setManifest] = useState<PreviewManifest | null>(null);
  const [assetFailed, setAssetFailed] = useState(false);
  useEffect(() => {
    const controller = new AbortController();
    fetch("/assets/previews/analyst/manifest.json", { signal: controller.signal, credentials: "omit" }).then(async response => {
      if (!response.ok) return;
      const data = parsePreviewManifest(await response.json());
      if (!controller.signal.aborted) setManifest(data);
    }).catch(() => { /* Static screenshots are optional; no AI request is made on home */ });
    return () => controller.abort();
  }, []);
  const images = assetFailed ? [] : manifest?.images.filter(item => item.locale === locale && item.theme === theme) || [];
  const picture = (kind: "main" | "analyst") => {
    const desktop = images.find(item => item.viewport === "desktop" && item.kind === kind);
    const mobile = images.find(item => item.viewport === "mobile" && item.kind === kind);
    if (!desktop || !mobile) return null;
    const detail = kind === "analyst";
    return <picture className={detail ? "hero-analyst-detail" : undefined}>
      <source media="(max-width: 767px)" type="image/webp" srcSet={`${mobile.src} ${mobile.width}w`} sizes="calc(100vw - 20px)" width={mobile.width / mobile.pixel_ratio} height={mobile.height / mobile.pixel_ratio}/>
      <img src={desktop.src} srcSet={`${desktop.src} ${desktop.width}w`} sizes={detail ? "(max-width: 767px) calc(100vw - 20px), 720px" : "(max-width: 1279px) calc(100vw - 48px), min(80vw, 1360px)"} width={desktop.width / desktop.pixel_ratio} height={desktop.height / desktop.pixel_ratio} alt={t(detail ? "screenshotDetail" : "screenshot")} loading={decorative || detail ? "lazy" : "eager"} fetchPriority={decorative || detail ? "low" : "high"} decoding="async" onError={() => setAssetFailed(true)}/>
    </picture>;
  };
  const main = picture(decorative ? "analyst" : "main");
  const artwork = main ? <>{main}{!decorative && <div className="hero-analyst-detail-section"><p>{t("screenshotDetail")}</p>{picture("analyst")}</div>}</> : <><img src="/assets/previews/quick-cam-1.webp" width={1920} height={1080} alt={t("frame")} loading={decorative ? "lazy" : "eager"} fetchPriority={decorative ? "low" : "high"} decoding="async"/><div className="hero-analyst-state"><Icon name="sparkles"/><span>{t(assetFailed ? "screenshotUnavailable" : "disabled")}</span></div></>;
  return <figure className={`hero-analyst-preview${main ? " has-screenshot" : ""}`} aria-label={decorative ? undefined : publicCopy("previewTitle")} aria-hidden={decorative || undefined}>
    {artwork}
    {!decorative && <figcaption><span>{main ? t("screenshot") : t("frame")}</span><Link to="/workspace/examples/quick-demo#analyst">{t("live")}<Icon name="arrow" size={17}/></Link></figcaption>}
  </figure>;
}
