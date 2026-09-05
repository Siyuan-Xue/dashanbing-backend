import { useEffect, useState } from "react";
import { WorkspaceSelect } from "../components/WorkspaceSelect";
import { useAnalystCopy } from "./copy";
import type { AnalystStyle } from "./types";

export function ContextControls({ style, open, onApply, onClose, disabled = false }: {
  style: AnalystStyle;
  open: boolean;
  onApply: (style: AnalystStyle) => void;
  onClose: () => void;
  disabled?: boolean;
}) {
  const t = useAnalystCopy();
  const [draftStyle, setDraftStyle] = useState(style);
  useEffect(() => { if (open) setDraftStyle(style); }, [open, style]);
  return <form className="analyst-context" onSubmit={event => {
    event.preventDefault();
    if (!disabled && draftStyle !== style) { onApply(draftStyle); onClose(); }
  }}>
    <label><span>{t("style")}</span><WorkspaceSelect disabled={disabled} value={draftStyle} onChange={event => setDraftStyle(event.target.value as AnalystStyle)}><option value="coach">{t("coach")}</option><option value="roast">{t("roast")}</option></WorkspaceSelect></label>
    <button className="button button-primary analyst-config-apply" type="submit" disabled={draftStyle === style || disabled}>{t("applyAnalysis")}</button>
  </form>;
}
