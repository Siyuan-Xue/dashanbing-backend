import { useEffect, useRef, useState } from "react";
import { analystApi } from "./api";
import type { AnalystLocale, AnalystSource, AnalystStyle, ReportState } from "./types";

export function useReport(source: AnalystSource, locale: AnalystLocale, style: AnalystStyle, ready = true) {
  const [state, setState] = useState<ReportState | null>(null);
  const [error, setError] = useState(false);
  const [busy, setBusy] = useState(false);
  const [revision, setRevision] = useState(0);
  const actionsRef = useRef<{ generate: () => Promise<void>; cancel: () => void } | null>(null);
  useEffect(() => {
    let controller = new AbortController();
    let timer: ReturnType<typeof setTimeout> | undefined;
    let disposed = false;
    let posting = false;
    let attempted = false;
    let latest: ReportState | null = null;
    setError(false); setBusy(false);
    const active = (request: AbortController) => !disposed && !request.signal.aborted;
    const cancel = () => { controller.abort(); clearTimeout(timer); };
    const receive = (value: ReportState) => {
      latest = value;
      setState(value);
      if (value.status === "queued" || value.status === "running") timer = setTimeout(() => void load(), 2000);
    };
    const generate = async (regenerate: boolean) => {
      if (disposed || posting || !ready || source.kind !== "task") return;
      // Lock synchronously: React's busy state alone cannot prevent two calls in one render.
      posting = true;
      attempted = true;
      cancel();
      const request = new AbortController(); controller = request;
      setBusy(true); setError(false);
      try {
        const value = await analystApi.generate(source, locale, style, regenerate, request.signal);
        if (active(request)) receive(value);
      } catch { if (active(request)) setError(true); }
      finally { if (active(request)) { posting = false; setBusy(false); } }
    };
    const load = async () => {
      const request = controller;
      try {
        const value = await analystApi.report(source, locale, style, request.signal);
        if (!active(request)) return;
        receive(value);
        // One automatic attempt per load/reload; waiting after POST or polling must not loop.
        if (value.status === "waiting" && !attempted && ready && source.kind === "task") await generate(false);
      } catch { if (active(request)) setError(true); }
    };
    const dispose = () => { disposed = true; cancel(); };
    actionsRef.current = { generate: () => generate(Boolean(latest?.report)), cancel: dispose };
    void load();
    return () => { dispose(); actionsRef.current = null; };
  }, [source.kind, source.id, locale, style, ready, revision]);
  const generate = async () => { await actionsRef.current?.generate(); };
  const reload = () => {
    actionsRef.current?.cancel();
    setState(null);
    setRevision(value => value + 1);
  };
  return { state, error, busy, generate, reload };
}
