import { ChangeEvent, DragEvent, useEffect, useRef, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";

import { Icon } from "../components/Icon";
import { PresetCards } from "../components/PresetCards";
import { WorkspaceState } from "../components/WorkspaceState";
import { useLocale } from "../providers/LocaleProvider";
import { useLoadable } from "../workspace/useLoadable";
import { uploadTaskInput, workspaceApi, WorkspaceApiError } from "../workspace/api";
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
  const [searchParams, setSearchParams] = useSearchParams();
  const draftId = searchParams.get("draft");
  const { value: presets, error: presetError, reload: reloadPresets } = useLoadable(workspaceApi.presets);
  const [title, setTitle] = useState("");
  const [mode, setMode] = useState<TaskMode>("quick");
  const [task, setTask] = useState<Task | null>(null);
  const [loading, setLoading] = useState(Boolean(draftId));
  const [loadError, setLoadError] = useState<Error | null>(null);
  const [revision, setRevision] = useState(0);
  const generationRef = useRef(0);
  const formRef = useRef({ title: "", mode: "quick" as TaskMode });
  const taskRef = useRef<Task | null>(null);
  const savedMetadataRef = useRef<Pick<Task, "title" | "mode"> | null>(null);
  const creatingRef = useRef<Promise<Task> | null>(null);
  const uploadQueueRef = useRef<Promise<void>>(Promise.resolve());
  const [uploads, setUploads] = useState<Partial<Record<TaskSlot, UploadState>>>({});
  const [submitError, setSubmitError] = useState("");
  const [titleError, setTitleError] = useState("");
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => () => { generationRef.current += 1; }, []);

  useEffect(() => {
    // Adding the newly created draft to the URL must not reset in-flight uploads.
    if (draftId && draftId === taskRef.current?.id && !loadError) return;
    const generation = ++generationRef.current;
    const controller = new AbortController();
    let timer: ReturnType<typeof setTimeout> | undefined;
    const current = () => generation === generationRef.current && !controller.signal.aborted;
    taskRef.current = null;
    savedMetadataRef.current = null;
    creatingRef.current = null;
    uploadQueueRef.current = Promise.resolve();
    formRef.current = { title: "", mode: "quick" };
    setTask(null); setTitle(""); setMode("quick"); setUploads({});
    setTitleError(""); setSubmitError(""); setLoadError(null); setSubmitting(false);
    setLoading(Boolean(draftId));
    if (!draftId) return;
    let initialized = false;
    const load = async () => {
      try {
        const restored = await workspaceApi.getTask(draftId, controller.signal);
        if (!current()) return;
        if (!["draft", "uploading"].includes(restored.status)) {
          navigate(`/workspace/tasks/${restored.id}`, { replace: true });
          return;
        }
        taskRef.current = restored;
        setTask(restored);
        if (!initialized) {
          savedMetadataRef.current = { title: restored.title, mode: restored.mode };
          formRef.current = { title: restored.title, mode: restored.mode };
          setTitle(restored.title); setMode(restored.mode);
          initialized = true;
        }
        setLoading(false);
        if (restored.status === "uploading") timer = setTimeout(() => void load(), 2000);
      } catch (error) {
        if (current()) { setLoadError(error instanceof Error ? error : new Error("Request failed")); setLoading(false); }
      }
    };
    void load();
    return () => { controller.abort(); if (timer) clearTimeout(timer); };
  }, [draftId, revision, navigate]);

  const ensureTask = async () => {
    if (taskRef.current) return taskRef.current;
    if (!creatingRef.current) {
      const generation = generationRef.current;
      const enteredTitle = formRef.current.title.trim();
      // Naming and uploading are independent, including while a name is being edited.
      const savedTitle = enteredTitle && Array.from(enteredTitle).length <= 120 ? enteredTitle : wt("defaultTitle");
      const creation = workspaceApi.createTask(savedTitle, formRef.current.mode).then((created) => {
        if (generation !== generationRef.current) throw new DOMException("Draft closed", "AbortError");
        taskRef.current = created;
        savedMetadataRef.current = { title: created.title, mode: created.mode };
        if (!formRef.current.title.trim()) {
          formRef.current.title = created.title;
          setTitle(created.title);
        }
        setTask(created);
        setSearchParams({ draft: created.id }, { replace: true });
        return created;
      }).finally(() => { if (creatingRef.current === creation) creatingRef.current = null; });
      creatingRef.current = creation;
    }
    return creatingRef.current;
  };

  const enqueue = <T,>(operation: () => Promise<T>) => {
    const write = uploadQueueRef.current.then(operation);
    uploadQueueRef.current = write.then(() => undefined, () => undefined);
    return write;
  };

  const saveFields = async () => {
    const existing = taskRef.current;
    const savedMetadata = savedMetadataRef.current;
    if (!existing || !savedMetadata) return;
    const generation = generationRef.current;
    const desired = { title: formRef.current.title.trim() || wt("defaultTitle"), mode: formRef.current.mode };
    if (Array.from(desired.title).length > 120) {
      setTitleError(wt("titleTooLong"));
      throw new Error(wt("titleTooLong"));
    }
    return enqueue(async () => {
      // Each draft queue retains its own last saved values even after navigation.
      if (savedMetadata.title === desired.title && savedMetadata.mode === desired.mode) return;
      const updated = await workspaceApi.updateDraft(existing.id, desired.title, desired.mode);
      savedMetadata.title = updated.title;
      savedMetadata.mode = updated.mode;
      if (generation === generationRef.current && taskRef.current) {
        // Metadata responses may predate a completed upload observed by polling.
        taskRef.current = { ...taskRef.current, title: updated.title, mode: updated.mode };
        setTask(taskRef.current);
        setSubmitError("");
      }
    });
  };

  const saveQuietly = () => {
    const generation = generationRef.current;
    void saveFields().catch(error => { if (generation === generationRef.current) setSubmitError(error instanceof Error ? error.message : wt("loadFailed")); });
  };

  useEffect(() => {
    if (!task?.id || submitting || (task.status !== "draft" && task.status !== "uploading")) return;
    const timer = setTimeout(saveQuietly, 400);
    return () => clearTimeout(timer);
  }, [title, mode, task?.id, submitting]);

  const upload = async (slot: TaskSlot, file: File) => {
    if (loading || submitting || loadError || uploads[slot]?.phase === "uploading" || taskRef.current?.status === "uploading") return;
    const generation = generationRef.current;
    const current = () => generation === generationRef.current;
    setSubmitError("");
    setUploads((previous) => ({ ...previous, [slot]: { file, progress: 0, phase: "uploading" } }));
    try {
      const currentTask = await ensureTask();
      await enqueue(async () => {
        if (!current()) return;
        const updated = await uploadTaskInput(currentTask.id, slot, file, (progress) => {
          if (current()) setUploads((previous) => ({ ...previous, [slot]: { file, progress, phase: "uploading" } }));
        });
        if (!current()) return;
        taskRef.current = updated;
        setTask(updated);
        setUploads((previous) => ({ ...previous, [slot]: { file, progress: 100, phase: "success" } }));
      });
    } catch (error) {
      if (!current()) return;
      const message = error instanceof WorkspaceApiError && error.validationIssues.some((issue) => issue.field === "title" && issue.type === "string_too_long")
        ? wt("titleTooLong") : error instanceof Error ? error.message : wt("uploadFailed");
      setUploads((previous) => ({ ...previous, [slot]: { file, progress: previous[slot]?.progress || 0, phase: "error", error: message } }));
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
    if (!task || !canSubmit || submitting) return;
    if (Array.from(title.trim()).length > 120) { setTitleError(wt("titleTooLong")); return; }
    const generation = generationRef.current;
    setSubmitting(true);
    setSubmitError("");
    try {
      await saveFields();
      const submitted = await workspaceApi.submitTask(task.id);
      if (generation === generationRef.current) navigate(`/workspace/tasks/${submitted.id}`);
    } catch (error) {
      if (generation !== generationRef.current) return;
      setSubmitError(error instanceof Error ? error.message : wt("loadFailed"));
      setSubmitting(false);
    }
  };

  if (loadError) return <div className="workspace-page"><WorkspaceState title={wt("detailError")} body={loadError.message} onRetry={() => setRevision(value => value + 1)}/></div>;
  if (loading) return <div className="workspace-page"><div className="loading-block page-loading" role="status" aria-label={wt("detailLoading")}/></div>;

  return <div className="workspace-page new-task-page">
    <header className="workspace-page-header"><div><h1>{wt("newTitle")}</h1><p>{wt("newBody")}</p></div></header>
    <section className="create-panel">
      <div className="create-fields">
        <label><span>{wt("taskTitle")}</span><input value={title} aria-invalid={Boolean(titleError)} disabled={submitting} onBlur={saveQuietly} onChange={(event) => { formRef.current.title = event.target.value; setTitle(event.target.value); setTitleError(""); }} placeholder={wt("defaultTitle")}/></label>
        <fieldset disabled={submitting}><legend>{wt("mode")}</legend><label><input type="radio" name="mode" checked={mode === "quick"} onChange={() => { formRef.current.mode = "quick"; setMode("quick"); saveQuietly(); }}/><span><b>{wt("quick")}</b><small>5–15 {wt("minutes")}</small></span></label><label><input type="radio" name="mode" checked={mode === "full"} onChange={() => { formRef.current.mode = "full"; setMode("full"); saveQuietly(); }}/><span><b>{wt("full")}</b><small>20–45 {wt("minutes")}</small></span></label></fieldset>
      </div>
      <div className="upload-grid">
        {TASK_SLOTS.map((slot) => {
          const state = uploads[slot];
          const serverInput = task?.inputs.find((item) => item.slot === slot);
          const disabled = submitting || task?.status === "uploading" || state?.phase === "uploading";
          const currentName = state?.phase === "success" ? state.file.name : serverInput?.original_filename;
          return <article className={`upload-card${state?.phase ? ` is-${state.phase}` : ""}`} key={slot}>
            <div className="upload-card-head"><span><Icon name={slot === "enrollment_video" ? "user" : "play"}/></span><div><h2>{slotLabels[locale][slot]}</h2></div></div>
            <label className={`upload-drop${disabled ? " is-disabled" : ""}`} title={currentName ? wt("replaceHint") : wt("uploadHint")} onDragOver={(event) => event.preventDefault()} onDrop={drop(slot)}>
              <input type="file" disabled={disabled} aria-required="true" accept="video/*,.mkv" aria-label={slotLabels[locale][slot]} onChange={choose(slot)}/>
              <Icon name={currentName ? "file" : "upload"}/>{currentName && <b>{currentName}</b>}{currentName ? !disabled && <small>{wt("replaceHint")}</small> : <span className="sr-only">{wt("uploadHint")}</span>}
            </label>
            {state?.phase === "uploading" && <div className="upload-progress" role="progressbar" aria-label={slotLabels[locale][slot]} aria-valuenow={state.progress} aria-valuemin={0} aria-valuemax={100}><i style={{ width: `${state.progress}%` }}/><span>{state.progress}%</span></div>}
            {state?.phase === "error" && <div className="upload-error" role="alert"><span>{state.error}</span><button type="button" aria-label={`${wt("retry")}${slotLabels[locale][slot]}`} title={`${wt("retry")}${slotLabels[locale][slot]}`} onClick={() => void upload(slot, state.file)}><Icon name="refresh"/></button></div>}
            {currentName && state?.phase !== "error" && state?.phase !== "uploading" && <div className="upload-success"><Icon name="check"/> {wt("uploaded")}</div>}
          </article>;
        })}
      </div>
      {(titleError || submitError) && <p className="inline-error" role="alert">{titleError || submitError}</p>}
      <div className="create-submit">{task && <small className="draft-note">{task.status === "uploading" ? wt("uploadingBody") : wt("draftHint")}</small>}<span>{wt("uploadCount")} {verified.size} / 5</span><button className="button button-primary" type="button" disabled={!canSubmit || submitting} onClick={() => void submit()}>{submitting ? wt("submitting") : wt("submit")} <Icon name="arrow"/></button></div>
    </section>
    <section className="workspace-section"><div className="workspace-section-heading"><h2>{wt("presetHeading")}</h2></div>{presetError ? <WorkspaceState title={wt("loadFailed")} body={presetError.message} onRetry={reloadPresets}/> : presets ? <PresetCards presets={presets}/> : <div className="loading-block" role="status" aria-label={wt("resultLoading")}/>}</section>
  </div>;
}
