import { WorkspaceSelect } from "../components/WorkspaceSelect";
import { useAnalystCopy } from "./copy";
import type { AnalystStyle, Subject } from "./types";

export function ContextControls({ style, subjectId, subjects, onStyle, onSubject, disabled = false }: {
  style: AnalystStyle; subjectId: string; subjects: Subject[];
  onStyle: (style: AnalystStyle) => void; onSubject: (id: string) => void; disabled?: boolean;
}) {
  const t = useAnalystCopy();
  return <div className="analyst-context">
    <label><span>{t("viewPlayer")}</span><WorkspaceSelect disabled={disabled} value={subjectId} onChange={event => onSubject(event.target.value)}><option value="">{t("all")}</option>{subjects.map(subject => <option key={subject.id} value={subject.id}>{subject.label}</option>)}</WorkspaceSelect></label>
    <label><span>{t("style")}</span><WorkspaceSelect disabled={disabled} value={style} onChange={event => onStyle(event.target.value as AnalystStyle)}><option value="coach">{t("coach")}</option><option value="roast">{t("roast")}</option></WorkspaceSelect></label>
  </div>;
}
