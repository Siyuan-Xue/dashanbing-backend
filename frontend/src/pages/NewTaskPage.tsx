import { ChangeEvent, DragEvent, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";

import { Icon } from "../components/Icon";
import { PresetCards } from "../components/PresetCards";
import { WorkspaceState } from "../components/WorkspaceState";
import { useLocale } from "../providers/LocaleProvider";
import { useLoadable } from "../workspace/useLoadable";
import { uploadTaskInput, workspaceApi } from "../workspace/api";
import { TASK_SLOTS } from "../workspace/types";
import type { Task, TaskMode, TaskSlot } from "../workspace/types";
import { useWorkspaceCopy } from "../workspace/useWorkspaceCopy";

type UploadState = { file: File; progress: number; phase: "uploading" | "error" | "success"; error?: string };

const slotLabels = {
  zh: { enrollment_video: "注册视频", cam_01: "机位 1", cam_02: "机位 2", cam_03: "机位 3", cam_04: "机位 4" },
  en: { enrollment_video: "Enrollment video", cam_01: "Camera 1", cam_02: "Camera 2", cam_03: "Camera 3", cam_04: "Camera 4" },
};

export function NewTaskPage() {
  const wt = useWorkspaceCopy();
  const { locale } = useLocale();
  const navigate = useNavigate();
  const { value: presets, error: presetError, reload: reloadPresets } = useLoadable(workspaceApi.presets);
  const [title, setTitle] = useState("");
  const [mode, setMode] = useState<TaskMode>("quick");
  const [task, setTask] = useState<Task | null>(null);
  const taskRef = useRef<Task | null>(null);
  const creatingRef = useRef<Promise<Task> | null>(null);
  const uploadQueueRef = useRef<Promise<void>>(Promise.resolve());
  const [uploads, setUploads] = useState<Partial<Record<TaskSlot, UploadState>>>({});
  const [submitError, setSubmitError] = useState("");
  const [submitting, setSubmitting] = useState(false);

  const ensureTask = async () => {
    if (taskRef.current) return taskRef.current;
    if (!creatingRef.current) {
      creatingRef.current = workspaceApi.createTask(title.trim() || wt("defaultTitle"), mode).then((created) => {
        taskRef.current = created;
        setTask(created);
        return created;
      }).finally(() => { creatingRef.current = null; });
    }
    return creatingRef.current;
  };

  const upload = async (slot: TaskSlot, file: File) => {
    setSubmitError("");
    setUploads((current) => ({ ...current, [slot]: { file, progress: 0, phase: "uploading" } }));
    try {
      const currentTask = await ensureTask();
      const write = uploadQueueRef.current.then(() => uploadTaskInput(currentTask.id, slot, file, (progress) => {
        setUploads((current) => ({ ...current, [slot]: { file, progress, phase: "uploading" } }));
      }));
      uploadQueueRef.current = write.then(() => undefined, () => undefined);
      const updated = await write;
      taskRef.current = updated;
      setTask(updated);
      setUploads((current) => ({ ...current, [slot]: { file, progress: 100, phase: "success" } }));
    } catch (error) {
      setUploads((current) => ({ ...current, [slot]: { file, progress: current[slot]?.progress || 0, phase: "error", error: error instanceof Error ? error.message : wt("uploadFailed") } }));
    }
  };

  const choose = (slot: TaskSlot) => (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (file) void upload(slot, file);
    event.target.value = "";
  };
  const drop = (slot: TaskSlot) => (event: DragEvent<HTMLLabelElement>) => {
    event.preventDefault();
    const file = event.dataTransfer.files[0];
    if (file) void upload(slot, file);
  };

  const verified = new Set(task?.inputs.filter((item) => item.validation_state === "valid").map((item) => item.slot));
  const canSubmit = task?.status === "draft" && TASK_SLOTS.every((slot) => verified.has(slot)) && !Object.values(uploads).some((item) => item?.phase === "uploading");

  const submit = async () => {
    if (!task || !canSubmit) return;
    setSubmitting(true);
    setSubmitError("");
    try {
      const submitted = await workspaceApi.submitTask(task.id);
      navigate(`/workspace/tasks/${submitted.id}`);
    } catch (error) {
      setSubmitError(error instanceof Error ? error.message : wt("loadFailed"));
      setSubmitting(false);
    }
  };

  return <div className="workspace-page new-task-page">
    <header className="workspace-page-header"><div><span className="page-eyebrow">NEW ANALYSIS</span><h1>{wt("newTitle")}</h1><p>{wt("newBody")}</p></div></header>
    <section className="create-panel">
      <div className="create-fields">
        <label><span>{wt("taskTitle")}</span><input value={title} disabled={Boolean(task)} onChange={(event) => setTitle(event.target.value)} placeholder={wt("defaultTitle")}/></label>
        <fieldset disabled={Boolean(task)}><legend>{wt("mode")}</legend><label><input type="radio" name="mode" checked={mode === "quick"} onChange={() => setMode("quick")}/><span><b>{wt("quick")}</b><small>5–15 min</small></span></label><label><input type="radio" name="mode" checked={mode === "full"} onChange={() => setMode("full")}/><span><b>{wt("full")}</b><small>20–45 min</small></span></label></fieldset>
      </div>
      <div className="upload-grid">
        {TASK_SLOTS.map((slot) => {
          const state = uploads[slot];
          const serverInput = task?.inputs.find((item) => item.slot === slot);
          const currentName = state?.phase === "success" ? state.file.name : serverInput?.original_filename;
          return <article className={`upload-card${state?.phase ? ` is-${state.phase}` : ""}`} key={slot}>
            <div className="upload-card-head"><span><Icon name={slot === "enrollment_video" ? "user" : "play"}/></span><div><h2>{slotLabels[locale][slot]}</h2><small>{slot}</small></div></div>
            <label className="upload-drop" onDragOver={(event) => event.preventDefault()} onDrop={drop(slot)}>
              <input type="file" accept="video/*,.mkv" aria-label={slotLabels[locale][slot]} onChange={choose(slot)}/>
              <Icon name={currentName ? "file" : "upload"}/><b>{currentName || wt("uploadHint")}</b>
              {currentName && <small>{wt("replace")}</small>}
            </label>
            {state?.phase === "uploading" && <div className="upload-progress" role="progressbar" aria-valuenow={state.progress} aria-valuemin={0} aria-valuemax={100}><i style={{ width: `${state.progress}%` }}/><span>{state.progress}%</span></div>}
            {state?.phase === "error" && <div className="upload-error" role="alert"><span>{state.error}</span><button type="button" aria-label={`${wt("retry")}${slotLabels[locale][slot]}`} onClick={() => void upload(slot, state.file)}><Icon name="refresh"/> {wt("retry")}</button></div>}
            {currentName && state?.phase !== "error" && <div className="upload-success"><Icon name="check"/> {wt("uploaded")}</div>}
          </article>;
        })}
      </div>
      {submitError && <p className="inline-error" role="alert">{submitError}</p>}
      <div className="create-submit"><span>{verified.size} / 5</span><button className="button button-primary" type="button" disabled={!canSubmit || submitting} onClick={() => void submit()}>{submitting ? wt("submitting") : wt("submit")} <Icon name="arrow"/></button></div>
    </section>
    <section className="workspace-section"><div className="section-heading compact"><span className="page-eyebrow">PRESETS</span><h2>{wt("presetHeading")}</h2><p>{wt("presetBody")}</p></div>{presetError ? <WorkspaceState title={wt("loadFailed")} body={presetError.message} onRetry={reloadPresets}/> : presets ? <PresetCards presets={presets}/> : <div className="loading-block" role="status"/>}</section>
  </div>;
}
