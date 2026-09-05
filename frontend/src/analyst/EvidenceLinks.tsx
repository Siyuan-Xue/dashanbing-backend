import { Icon } from "../components/Icon";
import { useAnalystCopy } from "./copy";
import type { Evidence } from "./types";
export function EvidenceLinks({ ids, evidence, onEvidence }: { ids: string[]; evidence: Evidence[]; onEvidence: (value: Evidence) => void }) {
  const t = useAnalystCopy();
  return <span className="evidence-links">{[...new Set(ids)].flatMap(id => {
    const item = evidence.find(value => value.id === id);
    if (!item || !Object.values(item.times_ms).some(time => typeof time === "number" && Number.isFinite(time) && time >= 0)) return [];
    const label = `${t("evidence")} · ${(item.time_ms / 1000).toFixed(1)}s`;
    return <button key={id} type="button" className="evidence-link" aria-label={label} title={label} onClick={() => onEvidence(item)}><Icon name="play" size={14}/>{(item.time_ms / 1000).toFixed(1)}s</button>;
  })}</span>;
}
