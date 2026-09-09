import { ChangeEvent, DragEvent, useEffect, useRef, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";

import { Icon } from "../components/Icon";
import { PresetCards } from "../components/PresetCards";
import { WorkspaceState } from "../components/WorkspaceState";
import { TaskConfiguration } from "../components/TaskConfiguration";
import { VideoSyncDialog } from "../components/VideoSyncDialog";
import { useLocale } from "../providers/LocaleProvider";
import { useLoadable } from "../workspace/useLoadable";
import { uploadTaskInput, workspaceApi, WorkspaceApiError } from "../workspace/api";
import { TASK_SLOTS } from "../workspace/types";
import type { TaskMode, TaskSlot } from "../workspace/types";
import { SYNC_CAMERAS } from "../lib/task-sync";
import type { ConfigurableTask as Task, RegistrationFields } from "../lib/task-sync";
import { useWorkspaceCopy } from "../workspace/useWorkspaceCopy";
import "../styles/video-sync.css";

type UploadState = { file: File; progress: number; phase: "uploading" | "error" | "success"; error?: string };
// The manual demo packs share a four-person, sequential enrollment video.
const registrationFor = (task?: Partial<RegistrationFields>): RegistrationFields => ({ enrollment_mode: task?.enrollment_mode || "sequential", expected_persons: task?.expected_persons ?? 4 });
// Keep the saved null distinct so a restored incomplete draft is patched before submission.
const savedRegistrationFor = (task: Partial<RegistrationFields>): RegistrationFields => ({ ...registrationFor(task), expected_persons: task.expected_persons ?? null });

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
  const [registration, setRegistration] = useState<RegistrationFields>(registrationFor());
  const [syncOpen, setSyncOpen] = useState(false);
  const [refreshingSync, setRefreshingSync] = useState(false);
  const [task, setTask] = useState<Task | null>(null);
  const [loading, setLoading] = useState(Boolean(draftId));
  const [loadError, setLoadError] = useState<Error | null>(null);
  const [revision, setRevision] = useState(0);
  const generationRef = useRef(0);
  const formRef = useRef({ title: "", mode: "quick" as TaskMode, ...registrationFor() });
  const taskRef = useRef<Task | null>(null);
  const savedMetadataRef = useRef<(Pick<Task, "title" | "mode" | "analyst_locale"> & RegistrationFields) | null>(null);
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
    formRef.current = { title: "", mode: "quick", ...registrationFor() };
    setTask(null); setTitle(""); setMode("quick"); setUploads({});
    setRegistration(registrationFor()); setSyncOpen(false); setRefreshingSync(false);
    setTitleError(""); setSubmitError(""); setLoadError(null); setSubmitting(false);
    setLoading(Boolean(draftId));
    if (!draftId) return;
    let initialized = false;
    const load = async () => {
      try {
        const restored = await workspaceApi.getTask(draftId, controller.signal);
        if (!current()) return;
        if (!["draft", "uploading", "failed", "interrupted"].includes(restored.status)) {
          navigate(`/workspace/tasks/${restored.id}`, { replace: true });
          return;
        }
        taskRef.current = restored;
        setTask(restored);
        if (!initialized) {
          savedMetadataRef.current = { title: restored.title, mode: restored.mode, analyst_locale: restored.analyst_locale || "zh", ...savedRegistrationFor(restored) };
          formRef.current = { title: restored.title, mode: restored.mode, ...registrationFor(restored) };
          setTitle(restored.title); setMode(restored.mode);
          setRegistration(registrationFor(restored));
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
      const creation = workspaceApi.createTask(savedTitle, formRef.current.mode, locale, registrationFor(formRef.current)).then((created) => {
        if (generation !== generationRef.current) throw new DOMException("Draft closed", "AbortError");
        taskRef.current = created;
        savedMetadataRef.current = { title: created.title, mode: created.mode, analyst_locale: locale, ...savedRegistrationFor(created) };
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
    if (!existing || !savedMetadata || !["draft", "uploading"].includes(existing.status)) return;
    const generation = generationRef.current;
    const desired = { ...formRef.current, title: formRef.current.title.trim() || wt("defaultTitle") };
    if (Array.from(desired.title).length > 120) {
      setTitleError(wt("titleTooLong"));
      throw new Error(wt("titleTooLong"));
    }
    return enqueue(async () => {
      // Each draft queue retains its own last saved values even after navigation.
      if (savedMetadata.title === desired.title && savedMetadata.mode === desired.mode && savedMetadata.analyst_locale === locale && savedMetadata.enrollment_mode === desired.enrollment_mode && savedMetadata.expected_persons === desired.expected_persons) return;
      const updated = await workspaceApi.updateDraft(existing.id, desired.title, desired.mode, locale, { enrollment_mode: desired.enrollment_mode, expected_persons: desired.expected_persons });
      savedMetadata.title = updated.title;
      savedMetadata.mode = updated.mode;
      savedMetadata.analyst_locale = locale;
      Object.assign(savedMetadata, savedRegistrationFor(updated));
      if (generation === generationRef.current && taskRef.current) {
        // Metadata responses may predate a completed upload observed by polling.
        taskRef.current = { ...taskRef.current, title: updated.title, mode: updated.mode, analyst_locale: locale, ...savedRegistrationFor(updated) };
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
  }, [title, mode, registration, locale, task?.id, submitting]);

  const upload = async (slot: TaskSlot, file: File) => {
    if (loading || submitting || syncOpen || loadError || uploads[slot]?.phase === "uploading" || (taskRef.current && taskRef.current.status !== "draft")) return;
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
  const uploading = Object.values(uploads).some((item) => item?.phase === "uploading");
  const canSync = task?.status === "draft" && SYNC_CAMERAS.every((slot) => verified.has(slot)) && !uploading;
  const canSubmit = canSync && !refreshingSync && TASK_SLOTS.every((slot) => verified.has(slot)) && registration.expected_persons !== null && task?.sync_status === "confirmed";
  const syncLabel = task?.sync_status === "confirmed" ? (locale === "zh" ? "已确认同步" : "Sync confirmed")
    : task?.sync_status === "stale" ? (locale === "zh" ? "视频已更换，请重新同步" : "Videos changed. Sync again")
    : (locale === "zh" ? "未确认同步" : "Sync unconfirmed");
  const changeRegistration = (patch: Partial<RegistrationFields>) => {
    Object.assign(formRef.current, patch);
    setRegistration(value => ({ ...value, ...patch }));
    saveQuietly();
  };

  const closeSync = async () => {
    setSyncOpen(false);
    const existing = taskRef.current;
    if (!existing) return;
    const generation = generationRef.current;
    setRefreshingSync(true);
    try {
      // Cancel discards local selections, but an external camera replacement must still be reflected.
      const refreshed = await workspaceApi.getTask(existing.id);
      if (generation === generationRef.current) { taskRef.current = refreshed; setTask(refreshed); }
    } catch (error) {
      if (generation === generationRef.current && taskRef.current) {
        taskRef.current = { ...taskRef.current, sync_status: "unconfirmed" }; setTask(taskRef.current);
        setSubmitError(error instanceof Error ? error.message : wt("loadFailed"));
      }
    } finally { if (generation === generationRef.current) setRefreshingSync(false); }
  };

  const reopen = async () => {
    if (!task || submitting) return;
    const generation = generationRef.current;
    setSubmitting(true); setSubmitError("");
    try {
      const updated = await workspaceApi.returnToInput(task.id);
      if (generation !== generationRef.current) return;
      taskRef.current = updated; setTask(updated);
    } catch (error) {
      if (generation === generationRef.current) setSubmitError(error instanceof Error ? error.message : wt("loadFailed"));
    } finally { if (generation === generationRef.current) setSubmitting(false); }
  };

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
      if (error instanceof WorkspaceApiError && error.status === 409) {
        try {
          const refreshed = await workspaceApi.getTask(task.id);
          if (generation === generationRef.current) { taskRef.current = refreshed; setTask(refreshed); }
        } catch { /* Keep the submission error visible if refreshing also fails. */ }
      }
      setSubmitting(false);
    }
  };

  if (loadError) return <div className="workspace-page"><WorkspaceState title={wt("detailError")} body={loadError.message} onRetry={() => setRevision(value => value + 1)}/></div>;
  if (loading) return <div className="workspace-page"><div className="loading-block page-loading" role="status" aria-label={wt("detailLoading")}/></div>;
  if (task && ["failed", "interrupted"].includes(task.status)) return <div className="workspace-page new-task-page"><section className="create-panel">
    <h1>{task.title}</h1><p>{locale === "zh" ? "返回输入后可修改注册方式、人数或视频，再次提交分析" : "Return to inputs to correct registration settings or videos and submit again."}</p>
    {submitError && <p role="alert" className="inline-error">{submitError}</p>}
    <button type="button" className="button button-primary" disabled={submitting} onClick={() => void reopen()}>{locale === "zh" ? "修改注册输入" : "Edit registration inputs"}</button>
  </section></div>;

  return <div className="workspace-page new-task-page">
    <header className="workspace-page-header"><div><h1>{wt("newTitle")}</h1><p>{wt("newBody")}</p></div></header>
    <section className="create-panel">
      <div className="create-fields">
        <label><span>{wt("taskTitle")}</span><input value={title} aria-invalid={Boolean(titleError)} disabled={submitting} onBlur={saveQuietly} onChange={(event) => { formRef.current.title = event.target.value; setTitle(event.target.value); setTitleError(""); }} placeholder={wt("defaultTitle")}/></label>
        <TaskConfiguration mode={mode} registration={registration} disabled={submitting}
          onModeChange={value => { formRef.current.mode = value; setMode(value); saveQuietly(); }}
          onRegistrationChange={changeRegistration}/>
      </div>
      <div className="upload-grid">
        {TASK_SLOTS.map((slot) => {
          const state = uploads[slot];
          const serverInput = task?.inputs.find((item) => item.slot === slot);
          const disabled = submitting || syncOpen || task?.status === "uploading" || state?.phase === "uploading";
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
      <div className="task-sync-summary"><div><strong>{locale === "zh" ? "四机位同步" : "Four-camera sync"}</strong><span role="status" className={task?.sync_status === "confirmed" ? "is-confirmed" : ""}>{syncLabel}</span><small>{!canSync ? (locale === "zh" ? "四个机位上传完成后可同步" : "Upload all four cameras to sync.") : (locale === "zh" ? "在四个画面中选定同一瞬间" : "Choose the same instant in all four views.")}</small></div><button className="button button-outline" type="button" disabled={!canSync || submitting} onClick={() => setSyncOpen(true)}>{locale === "zh" ? "同步视频" : "Sync videos"}</button></div>
      {(titleError || submitError) && <p className="inline-error" role="alert">{titleError || submitError}</p>}
      <div className="create-submit">{task && <small className="draft-note">{task.status === "uploading" ? wt("uploadingBody") : wt("draftHint")}</small>}<span>{wt("uploadCount")} {verified.size} / 5</span><button className="button button-primary" type="button" disabled={!canSubmit || submitting} onClick={() => void submit()}>{submitting ? wt("submitting") : wt("submit")} <Icon name="arrow"/></button></div>
    </section>
    {syncOpen && task && <VideoSyncDialog taskId={task.id} onClose={() => void closeSync()} onConfirmed={sync => {
      if (taskRef.current?.id !== task.id) return;
      taskRef.current = { ...taskRef.current, sync_status: sync.status };
      setTask(taskRef.current); setSyncOpen(false); setSubmitError("");
    }}/>}
    <section className="workspace-section"><div className="workspace-section-heading"><h2>{wt("presetHeading")}</h2></div>{presetError ? <WorkspaceState title={wt("loadFailed")} body={presetError.message} onRetry={reloadPresets}/> : presets ? <PresetCards presets={presets}/> : <div className="loading-block" role="status" aria-label={wt("resultLoading")}/>}</section>
  </div>;
}
