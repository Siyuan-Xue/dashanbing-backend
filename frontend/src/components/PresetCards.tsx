import { Link } from "react-router-dom";
import type { Preset } from "../workspace/types";
import { useWorkspaceCopy } from "../workspace/useWorkspaceCopy";

export function PresetCards({ presets }: { presets: Preset[] }) {
  const wt = useWorkspaceCopy();
  return <div className="preset-grid">{presets.map((preset, index) => (
    <article className={`preset-card preset-tone-${index + 1}`} data-testid="preset-card" key={preset.id}>
      <div className="preset-art" aria-hidden="true"><span/><i/><b>{String(index + 1).padStart(2, "0")}</b></div>
      <div className="preset-card-copy"><small>{preset.expected_minutes.toFixed(1)} MIN · {index === 0 ? "QUICK" : "FULL"}</small><h3>{preset.title}</h3><p>{preset.description}</p><Link to={`/workspace/examples/${preset.id}`}>{wt("viewPreset")} <span aria-hidden="true">→</span></Link></div>
    </article>
  ))}</div>;
}
