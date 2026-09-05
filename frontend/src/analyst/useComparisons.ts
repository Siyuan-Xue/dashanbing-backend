import { useEffect, useRef, useState } from "react";
import { analystApi } from "./api";
import type { AnalystLocale, AnalystSource, AnalystStyle, ComparisonReportState } from "./types";

// Comparison jobs have their own lifecycle and never reload or invalidate the session report.
export function useComparisons(source: AnalystSource, locale: AnalystLocale, style: AnalystStyle, contextKey: string) {
  const [items, setItems] = useState<ComparisonReportState[]>([]);
  const [error, setError] = useState(false); const [busy, setBusy] = useState(false);
  const actions = useRef<{ load: () => void; append: (id: string) => Promise<boolean> } | null>(null);
  useEffect(() => {
    let disposed = false, posting = false, revision = 0;
    let timer: ReturnType<typeof setTimeout> | undefined;
    let reader: AbortController | null = null;
    const writer = new AbortController();
    setItems([]); setError(false); setBusy(false);
    const poll = (values: ComparisonReportState[]) => {
      clearTimeout(timer);
      if (values.some(value => value.status === "queued" || value.status === "running")) timer = setTimeout(() => void load(), 2000);
    };
    const load = async () => {
      if (disposed || posting) return;
      reader?.abort(); reader = new AbortController();
      const signal = reader.signal, version = ++revision;
      try {
        const values = await analystApi.comparisons(source, locale, style, signal);
        if (!disposed && !signal.aborted && version === revision) { setItems(values); setError(false); poll(values); }
      } catch { if (!disposed && !signal.aborted && version === revision) setError(true); }
    };
    const append = async (id: string) => {
      if (disposed || posting) return false;
      posting = true; ++revision; reader?.abort(); clearTimeout(timer);
      setBusy(true); setError(false);
      try {
        const value = await analystApi.compare(source, id, locale, style, writer.signal);
        if (disposed) return false;
        setItems(previous => [...previous.filter(item => item.comparison_id !== value.comparison_id), value]);
        // Read all jobs again even if this one finished, to keep other queued comparisons polling.
        timer = setTimeout(() => void load(), 2000);
        return true;
      } catch { if (!disposed) setError(true); return false; }
      finally { posting = false; if (!disposed) setBusy(false); }
    };
    actions.current = { load: () => void load(), append };
    void load();
    return () => { disposed = true; writer.abort(); reader?.abort(); clearTimeout(timer); actions.current = null; };
  }, [source.kind, source.id, locale, style, contextKey]);
  return { items, error, busy, reload: () => actions.current?.load(), append: (id: string) => actions.current?.append(id) || Promise.resolve(false) };
}
