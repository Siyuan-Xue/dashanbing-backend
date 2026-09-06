import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { useAnalystCopy } from "../analyst/copy";
import { BrandMark } from "../components/Brand";
import { Icon } from "../components/Icon";
import { CameraEvidence, ExampleVisual, ProductPreview } from "../components/ProductPreview";
import { HeroAnalystPreview } from "../components/HeroAnalystPreview";
import { PublicHeader } from "../components/PublicHeader";
import { CopyKey } from "../copy";
import { useLocale } from "../providers/LocaleProvider";

const capabilities: Array<{ icon: "layers" | "basketball" | "clock"; title: CopyKey; body: CopyKey }> = [
  { icon: "layers", title: "capabilityOneTitle", body: "capabilityOneBody" },
  { icon: "basketball", title: "capabilityTwoTitle", body: "capabilityTwoBody" },
  { icon: "clock", title: "capabilityThreeTitle", body: "capabilityThreeBody" },
];

export function HomePage() {
  const { t } = useLocale();
  const at = useAnalystCopy();
  const [capability, setCapability] = useState(0);
  const main = useRef<HTMLElement>(null);
  const videoPreview = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const element = videoPreview.current;
    if (!element || typeof ResizeObserver === "undefined") return;
    // Follow the real video preview, including localized text and mobile layout.
    const syncSize = () => main.current?.style.setProperty("--home-preview-height", `${element.getBoundingClientRect().height}px`);
    syncSize();
    const observer = new ResizeObserver(syncSize);
    observer.observe(element);
    return () => observer.disconnect();
  }, []);
  return (
    <div className="public-site">
      <PublicHeader/>
      <main className="home-page" ref={main}>
        <section className="hero section-shell">
          <div className="hero-copy">
            <span className="eyebrow"><i/>{t("heroEyebrow")}</span>
            <h1>{t("heroTitle")}</h1>
            <p>{t("heroBody")}</p>
            <div className="hero-actions"><a className="button button-outline" href="#examples">{t("heroSecondary")}<Icon name="play" size={17}/></a><Link className="button button-primary" to="/workspace/new">{t("heroPrimary")}</Link></div>
          </div>
          <div className="hero-preview-wrap" ref={videoPreview}><div className="hero-glow"/><ProductPreview/></div>
        </section>

        <section className="ai-showcase" aria-labelledby="ai-showcase-title">
          <div className="section-shell">
            <div className="section-heading centered"><span className="eyebrow"><Icon name="sparkles" size={16}/>{at("title")}</span><h2 id="ai-showcase-title">{at("hero")}</h2><p>{at("heroDetails")}</p></div>
            <HeroAnalystPreview/>
          </div>
        </section>

        <section className="capabilities-section">
          <div className="section-shell">
            <div className="section-heading centered"><span className="eyebrow"><i/>{t("capabilitiesEyebrow")}</span><h2>{t("capabilitiesTitle")}</h2></div>
            <div className="capability-layout">
              <div className="capability-accordion">{capabilities.map((item, index) => <article data-testid="capability-card" className={`capability-card${capability === index ? " active" : ""}`} key={item.title}>
                <h3><button id={`capability-${index}-heading`} aria-expanded={capability === index} aria-controls={`capability-${index}-panel`} onClick={() => setCapability(index)}><Icon name={item.icon}/><span>{t(item.title)}</span><span className="accordion-indicator" aria-hidden="true"><Icon name={capability === index ? "minus" : "plus"} size={20}/></span></button></h3>
                <div id={`capability-${index}-panel`} role="region" aria-labelledby={`capability-${index}-heading`} hidden={capability !== index}><p>{t(item.body)}</p>{index === 2 && <p className="queue-description">{t("queueBody")}</p>}</div>
              </article>)}</div>
              <div className={`capability-visual capability-visual-${capability}`}>{capability === 2 ? <ProductPreview decorative/> : <CameraEvidence processed={capability === 1}/>}<div className="capability-caption"><Icon name={capabilities[capability].icon}/><span>{t(capabilities[capability].title)}</span></div></div>
            </div>
          </div>
        </section>

        <section className="examples-section section-shell" id="examples">
          <div className="section-heading centered"><span className="eyebrow"><i/>{t("examplesEyebrow")}</span><h2>{t("examplesTitle")}</h2><p>{t("examplesBody")}</p></div>
          <div className="example-grid">
            <article className="example-card" data-testid="public-example-card"><ExampleVisual/><div className="example-copy"><span>{t("quickTag")}</span><h3>{t("quickTitle")}</h3><p>{t("quickBody")}</p><Link to="/workspace/examples/quick-demo">{t("viewExample")}<Icon name="arrow"/></Link></div></article>
            <article className="example-card" data-testid="public-example-card"><ExampleVisual mixed/><div className="example-copy"><span>{t("mixedTag")}</span><h3>{t("mixedTitle")}</h3><p>{t("mixedBody")}</p><Link to="/workspace/examples/mixed-actions">{t("viewExample")}<Icon name="arrow"/></Link></div></article>
          </div>
        </section>

        <section className="cta section-shell"><div className="cta-panel"><div><h2>{t("ctaTitle")}</h2><p>{t("ctaBody")}</p></div><Link className="button button-primary" to="/workspace/new">{t("ctaAction")}<Icon name="arrow"/></Link></div></section>
      </main>
      <footer className="public-footer"><div className="section-shell"><div><BrandMark size={30}/><span>{t("footerLine")}</span></div><p>{t("footerNote")}</p></div></footer>
    </div>
  );
}
