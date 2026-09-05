import { useState } from "react";
import { Link } from "react-router-dom";
import { BrandMark } from "../components/Brand";
import { Icon } from "../components/Icon";
import { CameraEvidence, ExampleVisual, ProductPreview } from "../components/ProductPreview";
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
  const [capability, setCapability] = useState(0);
  return (
    <div className="public-site">
      <PublicHeader/>
      <main>
        <section className="hero section-shell">
          <div className="hero-copy">
            <span className="eyebrow"><i/>{t("heroEyebrow")}</span>
            <h1>{t("heroTitle")}</h1>
            <p>{t("heroBody")}</p>
            <div className="hero-actions"><a className="button button-outline" href="#examples">{t("heroSecondary")}<Icon name="play" size={17}/></a><Link className="button button-primary" to="/workspace/new">{t("heroPrimary")}</Link></div>
          </div>
          <div className="hero-preview-wrap"><div className="hero-glow"/><ProductPreview/></div>
        </section>

        <section className="capabilities-section">
          <div className="section-shell">
            <div className="section-heading centered"><span className="eyebrow"><i/>{t("capabilitiesEyebrow")}</span><h2>{t("capabilitiesTitle")}</h2></div>
            <div className="capability-layout">
              <div className="capability-accordion">{capabilities.map((item, index) => <article data-testid="capability-card" className={`capability-card${capability === index ? " active" : ""}`} key={item.title}>
                <h3><button id={`capability-${index}-heading`} aria-expanded={capability === index} aria-controls={`capability-${index}-panel`} onClick={() => setCapability(index)}><Icon name={item.icon}/><span>{t(item.title)}</span><span className="accordion-indicator" aria-hidden="true">{capability === index ? "−" : "+"}</span></button></h3>
                <div id={`capability-${index}-panel`} role="region" aria-labelledby={`capability-${index}-heading`} hidden={capability !== index}><p>{t(item.body)}</p>{index === 2 && <p className="queue-description">{t("queueBody")}</p>}</div>
              </article>)}</div>
              <div className={`capability-visual capability-visual-${capability}`}>{capability === 2 ? <ProductPreview decorative/> : <CameraEvidence processed={capability === 1}/>}<div className="capability-caption"><Icon name={capabilities[capability].icon}/><span>{t(capabilities[capability].title)}</span></div></div>
            </div>
          </div>
        </section>

        <section className="examples-section section-shell" id="examples">
          <div className="section-heading split"><div><span className="eyebrow"><i/>{t("examplesEyebrow")}</span><h2>{t("examplesTitle")}</h2></div><p>{t("examplesBody")}</p></div>
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
