import { useEffect, useRef, useState } from "react";
import { analystApi } from "./api";
import type { AnalystLocale, AnalystSource, AnalystStyle, ReportState } from "./types";

export function useReport(source: AnalystSource, locale: AnalystLocale, style: AnalystStyle) {
  const [state, setState] = useState<ReportState | null>(null);
  const [error, setError] = useState(false);
  const [busy, setBusy] = useState(false);
  const [revision, setRevision] = useState(0);
  const controllerRef = useRef<AbortController | null>(null);
  const timerRef = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);
  const generation = useRef(0);
  useEffect(() => {
    const current = ++generation.current;
    const controller = new AbortController(); controllerRef.current = controller;
    setError(false);
    const load = async () => {
      try {
        const value = await analystApi.report(source, locale, style, controller.signal);
        if (controller.signal.aborted || generation.current !== current) return;
        setState(value);
        if (value.status === "queued" || value.status === "running") timerRef.current = setTimeout(() => void load(), 2000);
      } catch { if (!controller.signal.aborted && generation.current === current) setError(true); }
    };
    void load();
    return () => { controller.abort(); clearTimeout(timerRef.current); };
  }, [source.kind, source.id, locale, style, revision]);
  const generate = async () => {
    if (busy || source.kind !== "task") return;
    clearTimeout(timerRef.current);
    controllerRef.current?.abort();
    const controller = new AbortController(); controllerRef.current = controller;
    const current = ++generation.current;
    setBusy(true); setError(false);
    try {
      const value = await analystApi.generate(source, locale, style, Boolean(state?.report), controller.signal);
      if (!controller.signal.aborted && generation.current === current) { setState(value); setRevision(value => value + 1); }
    } catch { if (!controller.signal.aborted && generation.current === current) setError(true); }
    finally { if (!controller.signal.aborted && generation.current === current) setBusy(false); }
  };
  useEffect(() => () => { controllerRef.current?.abort(); generation.current += 1; }, []);
  return { state, error, busy, generate, reload: () => { setState(null); setRevision(value => value + 1); } };
}
