import { BrandMark } from "./Brand";
import { Icon } from "./Icon";
import { useLocale } from "../providers/LocaleProvider";
import { useWorkspaceCopy } from "../workspace/useWorkspaceCopy";

const previews = "/assets/previews/";

/** A web workspace illustration built from the shipped quick-demo output. */
export function ProductPreview({ decorative = false }: { decorative?: boolean }) {
  const { t } = useLocale();
  const wt = useWorkspaceCopy();
  return <div className="product-preview" aria-label={decorative ? undefined : t("previewTitle")} aria-hidden={decorative || undefined}>
    <aside className="product-preview-sidebar">
      <div className="product-preview-brand"><BrandMark size={28}/><b>{t("brandPrimary")}</b><Icon name="menu" size={14}/></div>
      <span className="product-preview-nav"><Icon name="plus" size={16}/>{wt("createTask")}</span>
      <span className="product-preview-nav active"><Icon name="layers" size={16}/>{wt("tasks")}</span>
      <small>{wt("recent")}</small><span className="product-preview-recent"><i/>{t("quickTitle")}</span>
      <div className="product-preview-account"><span><Icon name="user" size={16}/></span><Icon name="github"/><Icon name="code" size={16}/><Icon name="settings" size={16}/></div>
    </aside>
    <div className="product-preview-content">
      <header><b>{t("previewTitle")}</b><span><Icon name="check" size={13}/>{t("previewStatus")}</span></header>
      <div className="product-preview-tabs" aria-hidden="true"><span className="active">{wt("phases")}</span>{(["cam1", "cam2", "cam3", "cam4"] as const).map(key => <span key={key}>{wt(key)}</span>)}</div>
      <figure className="product-preview-video"><img src={`${previews}quick-phases.webp`} width="1920" height="1080" alt={t("previewModelAlt")}/><figcaption>00:06 / 00:48</figcaption></figure>
      <div className="product-preview-tabs" aria-hidden="true"><span className="active">{wt("summary")}</span><span>{wt("timeline")}</span><span>JSON</span></div>
      <div className="product-preview-metrics">{([[wt("attempts"), 4], [wt("makes"), 2], [wt("participants"), 4], [wt("actionsCount"), 4]] as const).map(([label, value]) => <div key={label}><small>{label}</small><b>{value}</b></div>)}</div>
    </div>
  </div>;
}

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
