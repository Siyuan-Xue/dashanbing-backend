import { useEffect, useRef } from "react";
import { useWorkspaceCopy } from "../workspace/useWorkspaceCopy";

export function ConfirmDialog({ title, message, confirmLabel, danger = false, busy, onConfirm, onClose }: {
  title: string; message: string; confirmLabel: string; danger?: boolean; busy?: boolean; onConfirm: () => void; onClose: () => void;
}) {
  const wt = useWorkspaceCopy();
  const cancelRef = useRef<HTMLButtonElement>(null);
  useEffect(() => { cancelRef.current?.focus(); }, []);
  return <div className="dialog-backdrop" onMouseDown={(event) => { if (event.target === event.currentTarget) onClose(); }}>
    <section className="confirm-dialog" role="dialog" aria-modal="true" aria-labelledby="confirm-title">
      <span className={`dialog-icon${danger ? " danger" : ""}`} aria-hidden="true">!</span><h2 id="confirm-title">{title}</h2><p>{message}</p>
      <div><button ref={cancelRef} className="button button-outline" type="button" disabled={busy} onClick={onClose}>{wt("dismiss")}</button><button className={`button ${danger ? "button-danger" : "button-primary"}`} type="button" disabled={busy} onClick={onConfirm}>{confirmLabel}</button></div>
    </section>
  </div>;
}
