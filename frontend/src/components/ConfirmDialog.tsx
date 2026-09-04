import { useEffect, useRef } from "react";
import { useWorkspaceCopy } from "../workspace/useWorkspaceCopy";

export function ConfirmDialog({ title, message, confirmLabel, danger = false, busy, onConfirm, onClose }: {
  title: string; message: string; confirmLabel: string; danger?: boolean; busy?: boolean; onConfirm: () => void; onClose: () => void;
}) {
  const wt = useWorkspaceCopy();
  const cancelRef = useRef<HTMLButtonElement>(null);
  const dialogRef = useRef<HTMLElement>(null);
  useEffect(() => {
    const returnTarget = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    cancelRef.current?.focus();
    return () => { if (returnTarget?.isConnected) returnTarget.focus(); };
  }, []);
  useEffect(() => {
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape" && !busy) { event.preventDefault(); onClose(); return; }
      if (event.key !== "Tab") return;
      const focusable = [...(dialogRef.current?.querySelectorAll<HTMLElement>('button:not(:disabled), a[href], input:not(:disabled), select:not(:disabled), [tabindex]:not([tabindex="-1"])') || [])];
      if (!focusable.length) { event.preventDefault(); dialogRef.current?.focus(); return; }
      const first = focusable[0];
      const last = focusable.at(-1)!;
      if (!dialogRef.current?.contains(document.activeElement)) { event.preventDefault(); (event.shiftKey ? last : first).focus(); }
      else if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus(); }
      else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [busy, onClose]);
  return <div className="dialog-backdrop" onMouseDown={(event) => { if (!busy && event.target === event.currentTarget) onClose(); }}>
    <section ref={dialogRef} className="confirm-dialog" role="dialog" aria-modal="true" aria-labelledby="confirm-title" aria-describedby="confirm-message" tabIndex={-1}>
      <span className={`dialog-icon${danger ? " danger" : ""}`} aria-hidden="true">!</span><h2 id="confirm-title">{title}</h2><p id="confirm-message">{message}</p>
      <div><button ref={cancelRef} className="button button-outline" type="button" disabled={busy} onClick={onClose}>{wt("dismiss")}</button><button className={`button ${danger ? "button-danger" : "button-primary"}`} type="button" disabled={busy} onClick={onConfirm}>{confirmLabel}</button></div>
    </section>
  </div>;
}
