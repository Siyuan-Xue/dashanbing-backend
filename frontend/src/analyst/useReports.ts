import { useEffect, useRef, useState } from "react";
import { subscribeToSessionExpiry } from "../session";
import { analystApi } from "./api";
import type { AnalystLocale, AnalystSource, AnalystStyle, ReportCollection, ReportVariant } from "./types";

// Memory only: each account/source/locale owns a collection. Scope and style never cause I/O.
const cache = new Map<string, ReportCollection>();
subscribeToSessionExpiry(() => cache.clear());
const variantKey = (subjectId: string | null, style: AnalystStyle) => JSON.stringify([subjectId, style]);
const pending = (item: ReportVariant) => item.status === "queued" || item.status === "running";
function remember(key: string, value: ReportCollection) {
  cache.delete(key); cache.set(key, value);
  if (cache.size > 32) cache.delete(cache.keys().next().value!);
}
function merge(previous: ReportCollection | null, value: ReportCollection): ReportCollection {
  return { ...value, items: value.items.map(item => ({ ...item, report: item.report || previous?.items.find(old => old.subject_id === item.subject_id && old.style === item.style && old.locale === item.locale)?.report || null })) };
}

export function useReports(source: AnalystSource, locale: AnalystLocale, style: AnalystStyle, subjectId: string | null, ready = true, accountId?: number) {
  const key = JSON.stringify([accountId ?? null, source.kind, source.id, locale]);
  const [snapshot, setSnapshot] = useState<{ key: string; collection: ReportCollection | null }>({ key, collection: cache.get(key) || null });
  const [loadError, setLoadError] = useState(false);
  const [errors, setErrors] = useState<Set<string>>(new Set());
  const [writers, setWriters] = useState<Set<string>>(new Set());
  const [ensuring, setEnsuring] = useState(false);
  const actions = useRef<{ refresh: (subject: string | null, style: AnalystStyle) => Promise<void>; reload: () => void } | null>(null);
  useEffect(() => {
    let disposed = false, attempted = false, ensuringNow = false, readVersion = 0;
    let latest = cache.get(key) || null;
    let reader: AbortController | null = null;
    let timer: ReturnType<typeof setTimeout> | undefined;
    const posts = new Map<string, AbortController>();
    const ensureController = new AbortController();
    setSnapshot({ key, collection: latest }); setLoadError(false); setErrors(new Set()); setWriters(new Set()); setEnsuring(false);
    const publish = (value: ReportCollection) => {
      latest = merge(latest, value); remember(key, latest); setSnapshot({ key, collection: latest });
      schedule();
    };
    const schedule = () => {
      clearTimeout(timer);
      if (!disposed && latest?.items.some(pending)) timer = setTimeout(() => void load(), 2000);
    };
    const ensure = async () => {
      attempted = true; ensuringNow = true; setEnsuring(true);
      try {
        const value = await analystApi.ensureReports(source, locale, ensureController.signal);
        if (!disposed) publish(value);
      } catch { if (!disposed) setLoadError(true); }
      finally { ensuringNow = false; if (!disposed) setEnsuring(false); }
    };
    const load = async () => {
      if (disposed || ensuringNow) return;
      if (posts.size) { timer = setTimeout(() => void load(), 2000); return; }
      reader?.abort(); reader = new AbortController();
      const signal = reader.signal, version = ++readVersion;
      try {
        const value = await analystApi.reports(source, locale, signal);
        if (disposed || signal.aborted || version !== readVersion) return;
        setLoadError(false); publish(value);
        // Ensure the complete locale once, independently of the visible selection.
        if (!attempted && ready && source.kind === "task" && (!value.items.length || value.items.some(item => item.status === "waiting"))) await ensure();
      } catch { if (!disposed && !signal.aborted && version === readVersion) setLoadError(true); }
    };
    const refresh = async (subject: string | null, selectedStyle: AnalystStyle) => {
      const id = variantKey(subject, selectedStyle);
      const item = latest?.items.find(item => item.subject_id === subject && item.style === selectedStyle && item.locale === locale);
      if (disposed || !ready || source.kind !== "task" || ensuringNow || posts.has(id) || (item && (pending(item) || item.status === "disabled"))) return;
      const writer = new AbortController(); posts.set(id, writer);
      ++readVersion; reader?.abort(); clearTimeout(timer);
      setWriters(new Set(posts.keys())); setErrors(previous => new Set([...previous].filter(value => value !== id)));
      try {
        const value = await analystApi.generate(source, locale, selectedStyle, Boolean(item?.report), writer.signal, subject);
        if (disposed || writer.signal.aborted || !latest) return;
        const variant: ReportVariant = { ...value, subject_id: subject, locale, style: selectedStyle, report: value.report || item?.report || null };
        publish({ ...latest, items: [...latest.items.filter(item => variantKey(item.subject_id, item.style) !== id), variant] });
      } catch { if (!disposed && !writer.signal.aborted) setErrors(previous => new Set([...previous, id])); }
      finally { posts.delete(id); if (!disposed) { setWriters(new Set(posts.keys())); schedule(); } }
    };
    actions.current = { refresh, reload: () => { attempted = false; setErrors(new Set()); void load(); } };
    // Revalidate on entry/readiness changes; switching scope or style reuses the collection.
    void load();
    return () => { disposed = true; reader?.abort(); ensureController.abort(); posts.forEach(writer => writer.abort()); clearTimeout(timer); actions.current = null; };
  }, [key, source.kind, source.id, locale, ready]);
  const collection = snapshot.key === key ? snapshot.collection : cache.get(key) || null;
  const selectedKey = variantKey(subjectId, style);
  const state = collection?.items.find(item => item.subject_id === subjectId && item.locale === locale && item.style === style) || (collection ? { status: "waiting" as const, report: null, error: null } : null);
  return { collection, state, error: loadError || errors.has(selectedKey), busy: ensuring || writers.has(selectedKey),
    generate: () => actions.current?.refresh(subjectId, style), reload: () => actions.current?.reload() };
}
