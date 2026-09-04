import { Link } from "react-router-dom";
import { useLocale } from "../providers/LocaleProvider";
import { localizePreset } from "../workspace/labels";
import type { Preset } from "../workspace/types";
import { useWorkspaceCopy } from "../workspace/useWorkspaceCopy";

export function PresetCards({ presets }: { presets: Preset[] }) {
  const wt = useWorkspaceCopy();
  const { locale } = useLocale();
  return <div className="preset-grid">{presets.map((preset, index) => {
    const localized = localizePreset(locale, preset);
    return <article className={`preset-card preset-tone-${index + 1}`} data-testid="preset-card" key={preset.id}>
      <div className="preset-art" aria-hidden="true"><span/><i/><b>{String(index + 1).padStart(2, "0")}</b></div>
      <div className="preset-card-copy"><small>{preset.expected_minutes.toFixed(1)} MIN · {localized.tag}</small><h3>{localized.title}</h3><p>{localized.description}</p><Link to={`/workspace/examples/${preset.id}`}>{wt("viewPreset")} <span aria-hidden="true">→</span></Link></div>
    </article>
  })}</div>;
}
