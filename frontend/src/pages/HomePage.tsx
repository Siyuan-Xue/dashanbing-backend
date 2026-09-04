import { Link } from "react-router-dom";
import { BrandMark } from "../components/Brand";
import { Icon } from "../components/Icon";
import { PublicHeader } from "../components/PublicHeader";
import { CopyKey } from "../copy";
import { useLocale } from "../providers/LocaleProvider";

function WorkspacePreview() {
  const { t } = useLocale();
  return (
    <div className="workspace-preview" aria-label={t("previewTitle")}>
      <div className="preview-bar"><span/><span/><span/><b>{t("previewTitle")}</b><em>{t("previewStatus")}</em></div>
      <div className="preview-layout">
        <aside className="preview-sidebar">
          <BrandMark size={28}/>
          <span className="preview-nav active"><Icon name="chart" size={16}/></span>
          <span className="preview-nav"><Icon name="layers" size={16}/></span>
          <span className="preview-nav"><Icon name="clock" size={16}/></span>
        </aside>
        <section className="preview-main">
          <div className="preview-video">
            <div className="court-grid" aria-hidden="true"><i/><i/><i/><i/></div>
            <span className="player-dot one"/><span className="player-dot two"/><span className="player-dot three"/>
            <span className="tracking-line"/>
            <span className="preview-play" aria-hidden="true"><Icon name="play" size={18}/></span>
            <small>CAM 03 · 00:42</small>
          </div>
          <div className="preview-timeline"><span style={{ width: "68%" }}/><i style={{ left: "26%" }}/><i style={{ left: "51%" }}/><i style={{ left: "76%" }}/></div>
        </section>
        <aside className="preview-insights">
          <h3>{t("previewSummary")}</h3>
          <div className="metric-row"><span><small>{t("previewAttempts")}</small><strong>24</strong></span><span><small>{t("previewMakes")}</small><strong>15</strong></span><span><small>{t("previewPeople")}</small><strong>4</strong></span></div>
          <h4>{t("previewActions")}</h4>
          {["00:18", "00:42", "01:07"].map((time, index) => <div className="preview-event" key={time}><span>{index + 1}</span><i/><small>{time}</small></div>)}
        </aside>
      </div>
    </div>
  );
}

const capabilities: Array<{ icon: "layers" | "basketball" | "clock"; title: CopyKey; body: CopyKey }> = [
  { icon: "layers", title: "capabilityOneTitle", body: "capabilityOneBody" },
  { icon: "basketball", title: "capabilityTwoTitle", body: "capabilityTwoBody" },
  { icon: "clock", title: "capabilityThreeTitle", body: "capabilityThreeBody" },
];

function ExampleVisual({ mixed }: { mixed?: boolean }) {
  return <div className={`example-visual ${mixed ? "mixed" : "quick"}`} aria-hidden="true"><span className="mini-court"/><span className="mini-path"/><i className="mini-ball"/><div className="mini-stats"><b>{mixed ? "04" : "12"}</b><small>{mixed ? "actions" : "shots"}</small></div></div>;
}

export function HomePage() {
  const { t } = useLocale();
  return (
    <div className="public-site">
      <PublicHeader/>
      <main>
        <section className="hero section-shell">
          <div className="hero-copy">
            <span className="eyebrow"><i/>{t("heroEyebrow")}</span>
            <h1>{t("heroTitle")}</h1>
            <p>{t("heroBody")}</p>
            <div className="hero-actions"><Link className="button button-primary" to="/workspace/new">{t("heroPrimary")}<Icon name="arrow"/></Link><a className="button button-quiet" href="#examples"><Icon name="play"/>{t("heroSecondary")}</a></div>
            <div className="queue-note"><span><Icon name="clock"/></span><div><small>{t("queueLabel")}</small><strong>{t("queueTitle")}</strong><p>{t("queueBody")}</p></div></div>
          </div>
          <div className="hero-preview-wrap"><div className="hero-glow"/><WorkspacePreview/></div>
        </section>

        <section className="capabilities-section">
          <div className="section-shell">
            <div className="section-heading centered"><span className="eyebrow"><i/>{t("capabilitiesEyebrow")}</span><h2>{t("capabilitiesTitle")}</h2></div>
            <div className="capability-grid">{capabilities.map((item, index) => <article data-testid="capability-card" className="capability-card" key={item.title}><span className="card-number">0{index + 1}</span><div className="capability-icon"><Icon name={item.icon}/></div><h3>{t(item.title)}</h3><p>{t(item.body)}</p></article>)}</div>
          </div>
        </section>

        <section className="examples-section section-shell" id="examples">
          <div className="section-heading split"><div><span className="eyebrow"><i/>{t("examplesEyebrow")}</span><h2>{t("examplesTitle")}</h2></div><p>{t("examplesBody")}</p></div>
          <div className="example-grid">
            <article className="example-card" data-testid="public-example-card"><ExampleVisual/><div className="example-copy"><span>{t("quickTag")}</span><h3>{t("quickTitle")}</h3><p>{t("quickBody")}</p><Link to="/workspace/examples/quick-demo">{t("viewExample")}<Icon name="arrow"/></Link></div></article>
            <article className="example-card" data-testid="public-example-card"><ExampleVisual mixed/><div className="example-copy"><span>{t("mixedTag")}</span><h3>{t("mixedTitle")}</h3><p>{t("mixedBody")}</p><Link to="/workspace/examples/mixed-actions">{t("viewExample")}<Icon name="arrow"/></Link></div></article>
          </div>
        </section>

        <section className="cta section-shell"><div className="cta-panel"><div><h2>{t("ctaTitle")}</h2><p>{t("ctaBody")}</p></div><Link className="button button-inverse" to="/workspace/new">{t("ctaAction")}<Icon name="arrow"/></Link><span className="cta-ball" aria-hidden="true"/></div></section>
      </main>
      <footer className="public-footer"><div className="section-shell"><div><BrandMark size={30}/><span>{t("footerLine")}</span></div><p>{t("footerNote")}</p></div></footer>
    </div>
  );
}
