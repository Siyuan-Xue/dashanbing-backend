import { useEffect, useId, useRef, type ReactNode } from "react";
import { useAdminCopy } from "../lib/adminCopy";
import { Icon } from "./Icon";

export function AdminDialog({ title, children, busy, drawer, onClose }: { title: string; children: ReactNode; busy?: boolean; drawer?: boolean; onClose: () => void }) {
  const t = useAdminCopy();
  const id = useId();
  const dialog = useRef<HTMLElement>(null);
  const close = useRef<HTMLButtonElement>(null);
  useEffect(() => {
    const target = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    const overflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    close.current?.focus();
    return () => { document.body.style.overflow = overflow; if (target?.isConnected) target.focus(); };
  }, []);
  useEffect(() => {
    const handle = (event: KeyboardEvent) => {
      if (event.key === "Escape" && !busy) { event.preventDefault(); onClose(); }
      if (event.key !== "Tab") return;
      const nodes = [...(dialog.current?.querySelectorAll<HTMLElement>('button:not(:disabled), input:not(:disabled), select:not(:disabled), textarea:not(:disabled), a[href], [tabindex="0"]') || [])];
      const first = nodes[0]; const last = nodes.at(-1);
      if (!first || !last) { event.preventDefault(); dialog.current?.focus(); return; }
      if (!dialog.current?.contains(document.activeElement)) { event.preventDefault(); (event.shiftKey ? last : first).focus(); }
      else if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus(); }
      else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); }
    };
    window.addEventListener("keydown", handle);
    return () => window.removeEventListener("keydown", handle);
  }, [busy, onClose]);
  return <div className={`admin-dialog-backdrop${drawer ? " is-drawer" : ""}`} onMouseDown={event => { if (!busy && event.target === event.currentTarget) onClose(); }}><section ref={dialog} className={`admin-dialog${drawer ? " admin-drawer" : ""}`} role="dialog" aria-modal="true" aria-busy={busy || undefined} aria-labelledby={id} tabIndex={-1}><header><h2 id={id}>{title}</h2><button ref={close} className="table-action" type="button" disabled={busy} onClick={onClose} aria-label={t("close")} title={t("close")}><Icon name="x"/></button></header>{children}</section></div>;
}
