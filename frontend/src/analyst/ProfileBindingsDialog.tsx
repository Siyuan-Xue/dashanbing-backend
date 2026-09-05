import { useEffect, useId, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { WorkspaceSelect } from "../components/WorkspaceSelect";
import { useLocale } from "../providers/LocaleProvider";
import { analystApi } from "./api";
import type { AnalystContext, AnalystSource, ContextInput, TrainingProfile } from "./types";
import "../styles/profile-bindings.css";

const copy = {
  zh: {
    title: "绑定档案", team: "球队", unlinked: "未关联", unavailable: "已关联档案不可用",
    confirm: "确认", cancel: "取消", loading: "正在加载档案", saving: "正在保存",
    description: "确认后将本场训练记录存入对应档案",
    loadError: "档案加载失败，请重试", retry: "重试",
    saveError: "保存失败，选择已保留，请再次确认重试",
    duplicate: "每个球员档案只能关联本场一名球员，请调整重复绑定",
    empty: "暂无档案", profiles: "前往档案管理",
  },
  en: {
    title: "Bind profiles", team: "Team", unlinked: "Not linked", unavailable: "Linked profile unavailable",
    confirm: "Confirm", cancel: "Cancel", loading: "Loading profiles", saving: "Saving",
    description: "Confirm to save this session to the selected profiles",
    loadError: "Could not load profiles, please retry", retry: "Retry",
    saveError: "Could not save your choices, please confirm to try again",
    duplicate: "Each profile can be linked to only one player in this session",
    empty: "No profiles yet", profiles: "Manage profiles",
  },
};

export function ProfileBindingsDialog({ source, context, onSaved, onClose }: {
  source: AnalystSource;
  context: AnalystContext;
  onSaved: (value: AnalystContext) => void;
  onClose: () => void;
}) {
  const { locale } = useLocale();
  const t = copy[locale];
  const id = useId();
  // Each mount starts from the saved context; edits never mutate the caller's value.
  const [savedContext] = useState(context);
  const [draft, setDraft] = useState<ContextInput>(() => ({
    subjects: context.subjects.map(subject => ({ id: subject.id, profile_id: subject.profile_id || null })),
    team_profile_id: context.team_profile_id,
    comparison_id: context.comparison_id,
  }));
  const [profiles, setProfiles] = useState<TrainingProfile[] | null>(null);
  const [loadError, setLoadError] = useState(false);
  const [saveError, setSaveError] = useState(false);
  const [revision, setRevision] = useState(0);
  const [busy, setBusy] = useState(false);
  const savingRef = useRef(false);
  const controllerRef = useRef<AbortController | null>(null);
  const dialogRef = useRef<HTMLElement>(null);
  const cancelRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    const controller = new AbortController();
    setLoadError(false);
    setProfiles(null);
    analystApi.profiles(controller.signal)
      .then(value => { if (!controller.signal.aborted) setProfiles(value); })
      .catch(() => { if (!controller.signal.aborted) setLoadError(true); });
    return () => controller.abort();
  }, [revision]);

  useEffect(() => {
    const returnTarget = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    const previousOverflow = document.body.style.overflow;
    const controller = new AbortController();
    controllerRef.current = controller;
    document.body.style.overflow = "hidden";
    cancelRef.current?.focus();
    return () => {
      controller.abort();
      document.body.style.overflow = previousOverflow;
      if (returnTarget?.isConnected) returnTarget.focus();
    };
  }, []);

  useEffect(() => {
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape" && !savingRef.current) {
        event.preventDefault();
        onClose();
        return;
      }
      if (event.key !== "Tab") return;
      const focusable = [...(dialogRef.current?.querySelectorAll<HTMLElement>('button:not(:disabled), a[href]:not([aria-disabled="true"]), select:not(:disabled), [tabindex]:not([tabindex="-1"]):not(:disabled)') || [])];
      const first = focusable[0];
      const last = focusable.at(-1);
      if (!first || !last) {
        event.preventDefault();
        dialogRef.current?.focus();
      } else if (!dialogRef.current?.contains(document.activeElement)) {
        event.preventDefault();
        (event.shiftKey ? last : first).focus();
      } else if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [onClose]);

  const playerProfiles = profiles?.filter(profile => profile.kind === "player") || [];
  const teamProfiles = profiles?.filter(profile => profile.kind === "team") || [];
  const linkedPlayers = draft.subjects.flatMap(subject => subject.profile_id ? [subject.profile_id] : []);
  const duplicate = new Set(linkedPlayers).size !== linkedPlayers.length;
  const disabled = busy || profiles === null || loadError;

  const save = async () => {
    const controller = controllerRef.current;
    if (savingRef.current || disabled || duplicate || !controller || controller.signal.aborted) return;
    const bindingsChanged = draft.team_profile_id !== savedContext.team_profile_id
      || draft.subjects.some((subject, index) => subject.profile_id !== (savedContext.subjects[index].profile_id || null));
    if (!bindingsChanged) {
      onClose();
      return;
    }
    savingRef.current = true;
    setBusy(true);
    setSaveError(false);
    try {
      const value = await analystApi.updateContext(source, { ...draft, comparison_id: null }, controller.signal);
      if (!controller.signal.aborted) {
        onSaved(value);
        onClose();
      }
    } catch {
      if (!controller.signal.aborted) setSaveError(true);
    } finally {
      savingRef.current = false;
      if (!controller.signal.aborted) setBusy(false);
    }
  };

  return createPortal(<div className="profile-bindings-backdrop" onMouseDown={event => {
    if (event.target === event.currentTarget && !savingRef.current) onClose();
  }}>
    <section ref={dialogRef} className="profile-bindings-dialog" role="dialog" aria-modal="true" aria-busy={busy || undefined} aria-labelledby={`${id}-title`} aria-describedby={`${id}-description`} tabIndex={-1}>
      <h2 id={`${id}-title`}>{t.title}</h2>
      <div className="profile-bindings-fields">
        {draft.subjects.map((subject, index) => <label className="profile-bindings-row" key={subject.id}>
          <span>{locale === "en" ? savedContext.subjects[index].label.replace(/^球员\s*(\d+)$/, "Player $1") : savedContext.subjects[index].label}</span>
          <WorkspaceSelect disabled={disabled} value={subject.profile_id || ""} onChange={event => {
            const profileId = event.target.value || null;
            setDraft(current => ({ ...current, subjects: current.subjects.map(item => item.id === subject.id ? { ...item, profile_id: profileId } : item) }));
            setSaveError(false);
          }}>
            <option value="">{t.unlinked}</option>
            {subject.profile_id && !playerProfiles.some(profile => profile.id === subject.profile_id) && <option value={subject.profile_id} disabled>{t.unavailable}</option>}
            {playerProfiles.map(profile => <option key={profile.id} value={profile.id} disabled={draft.subjects.some(item => item.id !== subject.id && item.profile_id === profile.id)}>{profile.name}</option>)}
          </WorkspaceSelect>
        </label>)}
        <label className="profile-bindings-row profile-bindings-team">
          <span>{t.team}</span>
          <WorkspaceSelect disabled={disabled} value={draft.team_profile_id || ""} onChange={event => {
            setDraft(current => ({ ...current, team_profile_id: event.target.value || null }));
            setSaveError(false);
          }}>
            <option value="">{t.unlinked}</option>
            {draft.team_profile_id && !teamProfiles.some(profile => profile.id === draft.team_profile_id) && <option value={draft.team_profile_id} disabled>{t.unavailable}</option>}
            {teamProfiles.map(profile => <option key={profile.id} value={profile.id}>{profile.name}</option>)}
          </WorkspaceSelect>
        </label>
      </div>
      {profiles === null && !loadError && <p className="profile-bindings-status" role="status">{t.loading}</p>}
      {loadError && <div className="profile-bindings-feedback">
        <p role="alert">{t.loadError}</p>
        <button type="button" className="profile-bindings-retry" onClick={() => setRevision(value => value + 1)}>{t.retry}</button>
      </div>}
      {profiles?.length === 0 && <p className="profile-bindings-status">{t.empty} · <a href="/workspace/profiles" aria-disabled={busy || undefined} tabIndex={busy ? -1 : undefined} onClick={event => { if (savingRef.current) event.preventDefault(); }}>{t.profiles}</a></p>}
      {duplicate && <p className="profile-bindings-error" role="alert">{t.duplicate}</p>}
      {saveError && <p className="profile-bindings-error" role="alert">{t.saveError}</p>}
      <footer className="profile-bindings-footer">
        <p id={`${id}-description`}>{t.description}</p>
        <div className="profile-bindings-actions">
          {busy && <span className="profile-bindings-status" role="status">{t.saving}</span>}
          <button ref={cancelRef} className="profile-bindings-cancel" type="button" disabled={busy} onClick={() => { if (!savingRef.current) onClose(); }}>{t.cancel}</button>
          <button className="profile-bindings-confirm" type="button" disabled={disabled || duplicate} onClick={() => void save()}>{t.confirm}</button>
        </div>
      </footer>
    </section>
  </div>, document.body);
}
