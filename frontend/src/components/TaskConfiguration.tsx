import { useEffect, useId, useLayoutEffect, useRef, useState } from "react";
import { useLocation } from "react-router-dom";
import { useLocale } from "../providers/LocaleProvider";
import { useWorkspaceCopy } from "../workspace/useWorkspaceCopy";
import type { RegistrationFields } from "../lib/task-sync";
import type { TaskMode } from "../workspace/types";
import { Icon } from "./Icon";
import { WorkspaceSelect } from "./WorkspaceSelect";

type Props = {
  mode: TaskMode;
  registration: RegistrationFields;
  disabled: boolean;
  onModeChange: (mode: TaskMode) => void;
  onRegistrationChange: (patch: Partial<RegistrationFields>) => void;
};

export function TaskConfiguration({ mode, registration, disabled, onModeChange, onRegistrationChange }: Props) {
  const wt = useWorkspaceCopy();
  const { locale } = useLocale();
  const label = locale === "zh" ? "配置" : "Configure";
  const location = useLocation();
  const id = useId();
  const root = useRef<HTMLDivElement>(null);
  const trigger = useRef<HTMLButtonElement>(null);
  const panel = useRef<HTMLDivElement>(null);
  const [open, setOpen] = useState(false);
  const [placement, setPlacement] = useState({ above: false, maxHeight: 440 });
  useEffect(() => setOpen(false), [location.pathname]);
  useLayoutEffect(() => {
    if (!open) return;
    const position = () => {
      const anchor = trigger.current?.getBoundingClientRect();
      if (!anchor || !panel.current) return;
      const below = window.innerHeight - anchor.bottom - 24;
      const above = anchor.top - 24;
      const showAbove = below < panel.current.scrollHeight && above > below;
      setPlacement({ above: showAbove, maxHeight: Math.max(60, showAbove ? above : below) });
    };
    position();
    window.addEventListener("resize", position);
    window.addEventListener("scroll", position, true);
    return () => { window.removeEventListener("resize", position); window.removeEventListener("scroll", position, true); };
  }, [open]);
  useEffect(() => {
    if (!open) return;
    root.current?.querySelector<HTMLInputElement>('input:checked')?.focus({ preventScroll: true });
    const outside = (event: PointerEvent) => { if (!root.current?.contains(event.target as Node)) setOpen(false); };
    document.addEventListener("pointerdown", outside);
    return () => document.removeEventListener("pointerdown", outside);
  }, [open]);
  return <div ref={root} className="task-filter-control task-configuration" onBlur={event => {
    if (event.relatedTarget && !event.currentTarget.contains(event.relatedTarget)) setOpen(false);
  }} onKeyDown={event => {
    if (open && event.key === "Escape") { event.preventDefault(); event.stopPropagation(); setOpen(false); trigger.current?.focus(); }
  }}>
    <button ref={trigger} className="button button-quiet" type="button" disabled={disabled} aria-label={label} title={label} aria-expanded={open} aria-haspopup="dialog" aria-controls={id} onClick={() => setOpen(value => !value)}><Icon name="filter" size={18}/><span>{label}</span></button>
    {open && <div ref={panel} id={id} className="task-filter-popover task-configuration-popover" role="dialog" aria-label={label} style={{ top: placement.above ? "auto" : undefined, bottom: placement.above ? "calc(100% + 10px)" : undefined, maxHeight: placement.maxHeight }}>
      <fieldset disabled={disabled} className="task-mode-options"><legend>{wt("mode")}</legend>
        {(["quick", "full"] as const).map(value => <label key={value}><input type="radio" name="mode" checked={mode === value} onChange={() => onModeChange(value)}/><span><b>{wt(value)}</b><small>{value === "quick" ? "5–15" : "20–45"} {wt("minutes")}</small></span></label>)}
      </fieldset>
      <div className="task-registration-fields">
        <label><span>{locale === "zh" ? "注册方式" : "Registration method"}</span><WorkspaceSelect disabled={disabled} value={registration.enrollment_mode} onChange={event => onRegistrationChange({ enrollment_mode: event.target.value as RegistrationFields["enrollment_mode"] })}><option value="sequential">{locale === "zh" ? "依次注册" : "One at a time"}</option><option value="lineup">{locale === "zh" ? "并排注册" : "Line up together"}</option></WorkspaceSelect></label>
        <label><span>{locale === "zh" ? "注册人数" : "Number of people"}</span><WorkspaceSelect disabled={disabled} value={registration.expected_persons ?? ""} onChange={event => onRegistrationChange({ expected_persons: Number(event.target.value) })}>{[1, 2, 3, 4, 5, 6].map(count => <option key={count} value={count}>{count}</option>)}</WorkspaceSelect></label>
      </div>
      <p className="task-configuration-hint">{locale === "zh" ? "注册方式和人数应与视频一致" : "Match the registration method and headcount to your video"}</p>
    </div>}
  </div>;
}
