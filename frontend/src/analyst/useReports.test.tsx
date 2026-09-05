import { StrictMode } from "react";
import { act, cleanup, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, expect, test, vi } from "vitest";
import { notifySessionExpired } from "../session";
import { useReports } from "./useReports";
import type { AnalystLocale, AnalystSource, AnalystStyle, ReportCollection, ReportVariant } from "./types";
const task: AnalystSource = { kind: "task", id: "task 1" };
const variant = (subject_id: string | null, style: AnalystStyle): ReportVariant => ({ subject_id, style, locale: "en", status: "completed", error: null, report: { id: `${subject_id}-${style}`, summary: `${subject_id}-${style}`, highlights: [], players: [], comparison: null, suggestions: [], model: "fixture", locale: "en", style, created_at: "2026-09-05" } });
const collection: ReportCollection = { items: [variant(null, "coach"), variant(null, "roast"), variant("s1", "coach"), variant("s1", "roast")], subjects: [{ id: "s1", label: "Player 1" }], facts: { schema_version: 1, metrics: { action_counts: {}, shots: {}, registered_participant_count: 1, event_count: 0 }, subjects: [{ id: "s1", label: "Player 1" }], evidence: [], warnings: [], pose_available: false } };
const pending = { ...collection, items: collection.items.map(item => ({ ...item, report: null, status: "waiting" as const })) };
const writes = () => vi.mocked(fetch).mock.calls.filter(([, init]) => init?.method === "POST");
const settle = () => act(async () => {});
const advance = () => act(async () => { await vi.advanceTimersByTimeAsync(2000); });
function defer() { let resolve!: (value: Response) => void; const promise = new Promise<Response>(done => { resolve = done; }); return { promise, resolve }; }
function install(...values: (unknown | Promise<Response>)[]) {
  vi.stubGlobal("fetch", vi.fn(async () => { const value = values.shift(); if (value === undefined) throw new Error("Unexpected request"); return value instanceof Promise || value instanceof Response ? value : Response.json(value); }));
}
beforeEach(() => { notifySessionExpired(); vi.useFakeTimers({ toFake: ["setTimeout", "clearTimeout"] }); });
afterEach(() => { cleanup(); vi.useRealTimers(); vi.unstubAllGlobals(); });
test("cached player/style switching is synchronous and makes no additional reads or POST", async () => {
  install(collection);
  const { result, rerender } = renderHook(({ subject, style }: { subject: string | null; style: AnalystStyle }) => useReports(task, "en", style, subject, true, 7), { initialProps: { subject: null, style: "coach" } });
  await settle();
  rerender({ subject: "s1", style: "roast" });
  expect(result.current.state?.report?.summary).toBe("s1-roast");
  rerender({ subject: null, style: "coach" });
  expect(result.current.state?.report?.summary).toBe("null-coach");
  expect(fetch).toHaveBeenCalledTimes(1); expect(writes()).toHaveLength(0);
});
test("ensures all task variants once and polls while any variant is pending", async () => {
  const queued = { ...collection, items: collection.items.map(item => item.subject_id ? { ...item, report: null, status: "queued" as const } : item) };
  install(pending, queued, collection);
  const { result } = renderHook(() => useReports(task, "en", "coach", null, true, 7));
  await settle();
  expect(result.current.state?.report?.summary).toBe("null-coach");
  expect(writes()).toHaveLength(1);
  expect(writes()[0]).toEqual(["/api/v1/tasks/task%201/analyst/reports", expect.objectContaining({ method: "POST", body: JSON.stringify({ locale: "en" }) })]);
  await advance(); expect(result.current.collection).toEqual(collection);
  await advance(); expect(fetch).toHaveBeenCalledTimes(3);
});
test("does not loop POST when ensure returns waiting and does not generate on selection change", async () => {
  install(pending, pending);
  const { rerender } = renderHook(({ style }: { style: AnalystStyle }) => useReports(task, "en", style, null), { initialProps: { style: "coach" } });
  await settle(); rerender({ style: "roast" }); await advance();
  expect(writes()).toHaveLength(1); expect(fetch).toHaveBeenCalledTimes(2);
});
test("presets read the collection and never POST, including explicit refresh", async () => {
  install(pending);
  const { result } = renderHook(() => useReports({ kind: "preset", id: "demo" }, "en", "roast", "s1"));
  await settle(); await act(async () => { await result.current.generate(); });
  expect(fetch).toHaveBeenCalledWith("/api/v1/presets/demo/analyst/reports?locale=en", expect.anything());
  expect(writes()).toHaveLength(0);
});
test("readiness gates collection ensure and refresh", async () => {
  install(pending, pending, collection);
  const { result, rerender } = renderHook(({ ready }) => useReports(task, "en", "coach", null, ready), { initialProps: { ready: false } });
  await settle(); await act(async () => { await result.current.generate(); }); expect(writes()).toHaveLength(0);
  rerender({ ready: true }); await settle(); expect(writes()).toHaveLength(1);
  expect(result.current.state?.report?.summary).toBe("null-coach");
});
test("refreshes only the selected variant, retaining its old body through polling and failure", async () => {
  install(collection, { status: "queued", report: null, error: null }, { ...collection, items: collection.items.map(item => item.subject_id === "s1" && item.style === "coach" ? { ...item, status: "running", report: null } : item) }, { ...collection, items: collection.items.map(item => item.subject_id === "s1" && item.style === "coach" ? { ...item, status: "failed", report: null, error: "Try later" } : item) });
  const { result } = renderHook(() => useReports(task, "en", "coach", "s1"));
  await settle(); await act(async () => { await result.current.generate(); });
  expect(result.current.state).toMatchObject({ status: "queued", report: { summary: "s1-coach" } });
  await advance(); expect(result.current.state).toMatchObject({ status: "running", report: { summary: "s1-coach" } });
  await advance(); expect(result.current.state).toMatchObject({ status: "failed", report: { summary: "s1-coach" } });
  expect(writes()).toHaveLength(1);
  expect(JSON.parse(String(writes()[0][1]?.body))).toEqual({ locale: "en", style: "coach", regenerate: true, subject_id: "s1" });
});
test("deduplicates refresh clicks and tracks independent variants without cancelling on selection", async () => {
  const first = defer(), second = defer(); install(collection, first.promise, second.promise);
  const { result, rerender } = renderHook(({ style }: { style: AnalystStyle }) => useReports(task, "en", style, "s1"), { initialProps: { style: "coach" } });
  await settle(); act(() => { void result.current.generate(); void result.current.generate(); });
  expect(writes()).toHaveLength(1); expect(result.current.busy).toBe(true);
  rerender({ style: "roast" }); expect(result.current.busy).toBe(false);
  act(() => { void result.current.generate(); }); expect(writes()).toHaveLength(2);
  await act(async () => first.resolve(Response.json({ status: "queued", report: null, error: null })));
  expect(result.current.busy).toBe(true);
  await act(async () => second.resolve(Response.json({ ...variant("s1", "roast"), report: { ...variant("s1", "roast").report!, summary: "New roast" } })));
  expect(result.current.state?.report?.summary).toBe("New roast");
  rerender({ style: "coach" }); expect(result.current.state).toMatchObject({ status: "queued", report: { summary: "s1-coach" } });
});
test.each(["account", "source", "locale"])("isolates cached collections by %s and ignores late reads", async field => {
  const late = defer(); install(collection, late.promise, collection);
  const initialProps: { account: number; source: AnalystSource; locale: AnalystLocale } = { account: 7, source: task, locale: "en" };
  const { result, rerender } = renderHook(({ account, source, locale }) => useReports(source, locale, "coach", null, true, account), { initialProps });
  await settle();
  const changed = { ...initialProps, ...(field === "account" ? { account: 8 } : field === "source" ? { source: { kind: "preset" as const, id: task.id } } : { locale: "zh" as const }) };
  rerender(changed); expect(result.current.state).toBeNull();
  const signal = vi.mocked(fetch).mock.calls.at(-1)![1]!.signal!;
  rerender(initialProps); expect(result.current.state?.report?.summary).toBe("null-coach"); expect(signal.aborted).toBe(true);
  await act(async () => late.resolve(Response.json(pending))); await settle();
  expect(result.current.state?.report?.summary).toBe("null-coach"); expect(writes()).toHaveLength(0);
});
test("unmount aborts pending refresh and never writes a stale result to the cache", async () => {
  const late = defer(); install(collection, late.promise, new Promise<Response>(() => {}));
  const hook = renderHook(() => useReports(task, "en", "coach", null, true, 7)); await settle();
  act(() => { void hook.result.current.generate(); }); const signal = writes()[0][1]!.signal!;
  hook.unmount(); expect(signal.aborted).toBe(true);
  await act(async () => late.resolve(Response.json({ ...variant(null, "coach"), report: { ...variant(null, "coach").report!, summary: "Stale" } })));
  const next = renderHook(() => useReports(task, "en", "coach", null, true, 7));
  expect(next.result.current.state?.report?.summary).toBe("null-coach");
});
test("refresh errors stay with their variant and an explicit reload recovers the toolbar", async () => {
  install(collection, Response.json({ detail: "Unavailable" }, { status: 503 }), collection);
  const { result, rerender } = renderHook(({ style }: { style: AnalystStyle }) => useReports(task, "en", style, null), { initialProps: { style: "coach" } });
  await settle(); await act(async () => { await result.current.generate(); });
  expect(result.current.error).toBe(true); expect(result.current.state?.report?.summary).toBe("null-coach");
  rerender({ style: "roast" }); expect(result.current.error).toBe(false);
  rerender({ style: "coach" }); act(() => result.current.reload()); await settle();
  expect(result.current.error).toBe(false);
});
test("StrictMode replay ensures the collection only once", async () => {
  install(pending, pending, collection);
  const { result } = renderHook(() => useReports(task, "en", "coach", null), { wrapper: StrictMode });
  await settle(); expect(writes()).toHaveLength(1); expect(result.current.state?.report?.summary).toBe("null-coach");
});
