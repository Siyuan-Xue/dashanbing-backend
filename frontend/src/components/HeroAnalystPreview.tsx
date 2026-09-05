import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { Icon } from "./Icon";
import { useLocale } from "../providers/LocaleProvider";
import { useTheme } from "../providers/ThemeProvider";
import { useAnalystCopy } from "../analyst/copy";
import { parsePreviewManifest } from "../analyst/previewManifest";
import type { PreviewManifest } from "../analyst/previewManifest";

export function HeroAnalystPreview({ decorative = false }: { decorative?: boolean }) {
  const { locale } = useLocale(); const { theme } = useTheme(); const t = useAnalystCopy();
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
      <img src={desktop.src} srcSet={`${desktop.src} ${desktop.width}w`} sizes="(max-width: 767px) calc(100vw - 20px), (max-width: 1279px) calc(100vw - 48px), min(100vw - 48px, 1120px)" width={desktop.width / desktop.pixel_ratio} height={desktop.height / desktop.pixel_ratio} alt={t(detail ? "screenshotDetail" : "screenshot")} loading="lazy" decoding="async" onError={() => setAssetFailed(true)}/>
    </picture>;
  };
  const main = picture("analyst");
  const artwork = main ? main : <><img src="/assets/previews/quick-cam-1.webp" width={1920} height={1080} alt={t("frame")} loading="lazy" decoding="async"/><div className="hero-analyst-state"><Icon name="sparkles"/><span>{t("screenshotUnavailable")}</span></div></>;
  return <figure className={`hero-analyst-preview${main ? " has-screenshot" : ""}`} aria-label={decorative ? undefined : t("screenshot")} aria-hidden={decorative || undefined}>
    {artwork}
    {!decorative && <figcaption><Link to="/workspace/examples/quick-demo#analyst">{t("live")}<Icon name="arrow" size={17}/></Link></figcaption>}
  </figure>;
}
