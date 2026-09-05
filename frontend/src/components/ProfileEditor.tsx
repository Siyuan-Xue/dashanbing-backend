import { useEffect, useId, useRef, useState } from "react";
import { WorkspaceSelect } from "./WorkspaceSelect";
import { analystApi } from "../analyst/api";
import { useAnalystCopy } from "../analyst/copy";
import type { ProfileInput, TrainingProfile } from "../analyst/types";

export function ProfileEditor({ profile, onSaved, onClose }: { profile: TrainingProfile | null; onSaved: (value: TrainingProfile) => void; onClose: () => void }) {
  const t = useAnalystCopy();
  const titleId = useId();
  const dialogRef = useRef<HTMLFormElement>(null);
  const nameRef = useRef<HTMLInputElement>(null);
  const [draft, setDraft] = useState<ProfileInput>({ kind: profile?.kind || "player", name: profile?.name || "", goals: profile?.goals || "", notes: profile?.notes || "" });
  const [error, setError] = useState(false); const [busy, setBusy] = useState(false);
  const active = useRef(true); const saving = useRef(false);
  useEffect(() => { active.current = true; return () => { active.current = false; }; }, []);
  useEffect(() => {
    const returnTarget = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    nameRef.current?.focus();
    return () => {
      document.body.style.overflow = previousOverflow;
      if (returnTarget?.isConnected) returnTarget.focus();
    };
  }, []);
  useEffect(() => {
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape" && !saving.current) { event.preventDefault(); onClose(); return; }
      if (event.key !== "Tab") return;
      const elements = [...(dialogRef.current?.querySelectorAll<HTMLElement>('button, input, select, textarea, [tabindex="0"]') || [])].filter(element => !element.matches(":disabled"));
      const first = elements[0]; const last = elements.at(-1);
      if (!first) { event.preventDefault(); dialogRef.current?.focus(); return; }
      if (!dialogRef.current?.contains(document.activeElement)) { event.preventDefault(); (event.shiftKey ? last : first)?.focus(); }
      else if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last?.focus(); }
      else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [onClose]);
  const save = async () => {
    if (saving.current || !draft.name.trim()) return;
    saving.current = true; setBusy(true); setError(false);
    try {
      const body = { name: draft.name.trim(), goals: draft.goals, notes: draft.notes };
      const value = profile ? await analystApi.updateProfile(profile.id, body) : await analystApi.createProfile({ kind: draft.kind, ...body });
      if (active.current) onSaved(value);
    } catch { if (active.current) setError(true); }
    finally { if (active.current) { setBusy(false); saving.current = false; } }
  };
  return <div className="dialog-backdrop" onMouseDown={event => { if (event.target === event.currentTarget && !saving.current) onClose(); }}><form ref={dialogRef} role="dialog" aria-modal="true" aria-busy={busy || undefined} aria-labelledby={titleId} tabIndex={-1} className="profile-editor profile-editor-dialog" onSubmit={event => { event.preventDefault(); void save(); }}><h2 id={titleId}>{t(profile ? "editProfile" : "newProfile")}</h2>
    <fieldset disabled={busy}><label><span>{t("kind")}</span><WorkspaceSelect value={draft.kind} disabled={Boolean(profile)} onChange={event => setDraft({ ...draft, kind: event.target.value as ProfileInput["kind"] })}><option value="player">{t("playerKind")}</option><option value="team">{t("teamKind")}</option></WorkspaceSelect></label>
    <label><span>{t("name")}</span><input required maxLength={120} ref={nameRef} value={draft.name} onChange={event => setDraft({ ...draft, name: event.target.value })}/></label>
    <label><span>{t("goals")}</span><textarea rows={3} maxLength={4000} value={draft.goals} onChange={event => setDraft({ ...draft, goals: event.target.value })}/></label>
    <label><span>{t("notes")}</span><textarea placeholder={t("notesHelp")} rows={4} maxLength={8000} value={draft.notes} onChange={event => setDraft({ ...draft, notes: event.target.value })}/></label></fieldset>
    {error && <p className="analyst-error" role="alert">{t("saveError")}</p>}
    <div className="profile-editor-actions"><button className="button button-outline" type="button" disabled={busy} onClick={onClose}>{t("cancel")}</button><button className="button button-primary" disabled={busy || !draft.name.trim()} type="submit">{t("save")}</button></div>
  </form></div>;
}
