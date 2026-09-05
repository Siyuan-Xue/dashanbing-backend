import { useLocale } from "../providers/LocaleProvider";
export { HeroAnalystPreview as ProductPreview } from "./HeroAnalystPreview";

const previews = "/assets/previews/";

export function CameraEvidence({ processed = false }: { processed?: boolean }) {
  const { t, locale } = useLocale();
  return processed
    ? <figure className="model-evidence"><img src={`${previews}quick-pose.webp`} width="1920" height="1080" loading="lazy" alt={t("previewPoseAlt")}/><figcaption>{t("previewPoseCaption")}</figcaption></figure>
    : <div className="camera-evidence">{[1, 2, 3, 4].map(camera => <figure key={camera}><img src={`${previews}quick-cam-${camera}.webp`} width="1920" height="1080" loading="lazy" alt={`${locale === "zh" ? "真实篮球训练 · 机位" : "Basketball training · Camera"} ${camera}`}/><figcaption>{locale === "zh" ? "机位" : "Camera"} {camera}</figcaption></figure>)}</div>;
}

export function ExampleVisual({ mixed = false }: { mixed?: boolean }) {
  const { t } = useLocale();
  return <figure className="example-visual"><img src={`${previews}${mixed ? "mixed" : "quick"}-phases.webp`} width="1920" height="1080" loading="lazy" alt={mixed ? t("previewMixedAlt") : t("previewModelAlt")}/></figure>;
}
