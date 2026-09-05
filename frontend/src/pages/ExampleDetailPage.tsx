import { WorkspaceSelect } from "../components/WorkspaceSelect";
import { useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";

import { AnalystAnchor } from "../analyst/AnalystPanel";
import { useAuth } from "../providers/AuthProvider";
import { Icon } from "../components/Icon";
import { ResultWorkspace } from "../components/ResultWorkspace";
import { WorkspaceState } from "../components/WorkspaceState";
import { useLocale } from "../providers/LocaleProvider";
import { workspaceApi } from "../workspace/api";
import { localizePreset } from "../workspace/labels";
import type { TaskMode } from "../workspace/types";
import { useLoadable } from "../workspace/useLoadable";
import { useWorkspaceCopy } from "../workspace/useWorkspaceCopy";

export function ExampleDetailPage() {
  const { presetId = "" } = useParams();
  const wt = useWorkspaceCopy();
  const { user } = useAuth();
  const { locale } = useLocale();
  const navigate = useNavigate();
  const { value: presets, error: presetError, reload: reloadPresets } = useLoadable(workspaceApi.presets);
  const { value: result, error: resultError, reload: reloadResult, loading } = useLoadable(() => workspaceApi.presetResult(presetId), [presetId]);
  const [mode, setMode] = useState<TaskMode>("quick");
  const [creating, setCreating] = useState(false);
  const [createError, setCreateError] = useState("");
  const preset = presets?.find((item) => item.id === presetId);
  const localizedPreset = preset ? localizePreset(locale, preset) : null;

  const create = async () => {
    setCreating(true); setCreateError("");
    try { const created = await workspaceApi.createFromPreset(presetId, mode, locale); navigate(`/workspace/tasks/${created.id}`); }
    catch (reason) { setCreateError(reason instanceof Error ? reason.message : wt("loadFailed")); setCreating(false); }
  };

  if (presetError) return <div className="workspace-page"><WorkspaceState title={wt("loadFailed")} body={presetError.message} onRetry={reloadPresets}/></div>;
  return <div className="workspace-page example-detail-page">
    <header className="detail-header example-header">
      <div className="detail-heading"><Link to="/workspace/new" className="back-link" aria-label={wt("presetHeading")} title={wt("presetHeading")}><Icon name="chevronLeft"/></Link><h1 title={localizedPreset?.title || presetId}>{localizedPreset?.title || presetId}</h1></div>
      <div className="preset-run"><AnalystAnchor/><label className="preset-mode"><span className="sr-only">{wt("mode")}</span><WorkspaceSelect value={mode} onChange={(event) => setMode(event.target.value as TaskMode)}><option value="quick">{wt("quick")}</option><option value="full">{wt("full")}</option></WorkspaceSelect></label><button className="button button-primary" disabled={creating} onClick={() => void create()}>{creating ? wt("creatingPreset") : wt("createTask")}</button></div>
    </header>
    {createError && <p className="task-error-banner" role="alert">{createError}</p>}
    <ResultWorkspace analystSource={{ kind: "preset", id: presetId }} accountId={user?.id} key={presetId} result={result} resultLoading={loading} resultError={resultError} onRetryResult={reloadResult}/>
  </div>;
}
