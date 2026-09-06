import { Link } from "react-router-dom";
import { Icon } from "./Icon";
import { ProductPreviewSidebar } from "./ProductPreview";
import { useLocale } from "../providers/LocaleProvider";
import { useAnalystCopy } from "../analyst/copy";

// A concise website illustration, not a screenshot or a generated report.
// Numbers and camera frames come from the existing quick-demo sample.
export function HeroAnalystPreview({ decorative = false }: { decorative?: boolean }) {
  const { locale } = useLocale(); const t = useAnalystCopy();
  const zh = locale === "zh";
  return <figure className="hero-analyst-preview" aria-hidden={decorative || undefined}>
    <div className="product-preview ai-preview-frame" role="img" aria-label={zh ? "AI 分析师功能示意：本场复盘、视频证据、训练建议与追问" : "AI analyst illustration: session review, video evidence, practice advice and follow-ups"}>
      <ProductPreviewSidebar/>
      <div className="ai-preview-content">
        <header><strong><Icon name="sparkles" size={20}/>{t("title")}</strong><span>{t("coach")}<Icon name="chevronDown" size={13}/></span></header>
        <div className="ai-preview-report">
          <div className="ai-preview-intro"><small>{zh ? "本场复盘" : "Session review"}</small><h3>{zh ? "每一球，都有下一步" : "Every shot has a next step"}</h3><p>{zh ? "找到值得重看的片段，把复盘变成下一场的练习" : "Find the plays worth revisiting and turn your review into practice"}</p></div>
          <div className="ai-preview-stats">{(zh ? [["跳投", "4"], ["命中", "2"], ["命中率", "50%"]] : [["Jump shots", "4"], ["Made", "2"], ["Make rate", "50%"]]).map(([label, value]) => <div key={label}><b>{value}</b><span>{label}</span></div>)}</div>
          <div className="ai-preview-evidence"><h4><Icon name="play" size={15}/>{zh ? "回到画面，看看细节" : "Revisit the details"}</h4><div className="ai-preview-cameras">{[1, 3].map(camera => <div key={camera}><img src={`/assets/previews/quick-cam-${camera}.webp`} alt="" width={1920} height={1080} loading="lazy"/><span><Icon name="play" size={13}/>{zh ? "机位" : "Camera"} {camera}</span></div>)}</div></div>
          <div className="ai-preview-practice"><Icon name="basketball" size={20}/><div><h4>{t("suggestions")}</h4><p>{zh ? "对照命中与偏出的片段，下一组带着问题上场" : "Compare makes and misses, then take one focus into your next set"}</p></div></div>
        </div>
        <div className="ai-preview-chat"><Icon name="chat" size={17}/><span>{t("quickPractice")}</span><span className="ai-preview-send"><Icon name="arrow" size={17}/></span></div>
      </div>
    </div>
    {!decorative && <figcaption><Link to="/workspace/examples/quick-demo#analyst">{t("live")}<Icon name="arrow" size={17}/></Link></figcaption>}
  </figure>;
}
