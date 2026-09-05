import { StrictMode } from "react";
import { act, cleanup, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, expect, test, vi } from "vitest";
import type { AnalystLocale, AnalystSource, AnalystStyle, ReportState } from "./types";
import { useReport } from "./useReport";

const task: AnalystSource = { kind: "task", id: "training 1" };
const waiting: ReportState = { status: "waiting", report: null, error: null };
const queued: ReportState = { ...waiting, status: "queued" };
const running: ReportState = { ...waiting, status: "running" };
const failed: ReportState = { ...waiting, status: "failed", error: "Generation failed" };
const disabled: ReportState = { ...waiting, status: "disabled" };
const completed: ReportState = {
  status: "completed", error: null,
  report: { id: "report-1", summary: "Practice your release", highlights: [], players: [], comparison: null,
    suggestions: ["Repeat the drill"], model: "test-model", locale: "en", style: "roast", created_at: "2026-09-05T01:00:00Z" },
};
const json = (value: unknown, status = 200) => new Response(JSON.stringify(value), { status, headers: { "Content-Type": "application/json" } });
function deferredResponse() {
  let resolve!: (value: Response) => void;
  const promise = new Promise<Response>(done => { resolve = done; });
  return { promise, resolve };
}
function install(...responses: (ReportState | Response | Promise<Response>)[]) {
  const fetcher = vi.fn(async (_input: RequestInfo | URL, _init?: RequestInit) => {
    const response = responses.shift();
    if (!response) throw new Error("Unexpected extra report request");
    return response instanceof Response || response instanceof Promise ? response : json(response);
  });
  vi.stubGlobal("fetch", fetcher);
  return fetcher;
}
const settle = () => act(async () => {});
const advance = (ms = 2000) => act(async () => { await vi.advanceTimersByTimeAsync(ms); });
const posts = () => vi.mocked(fetch).mock.calls.filter(([, init]) => init?.method === "POST");
beforeEach(() => { vi.useFakeTimers({ toFake: ["setTimeout", "clearTimeout"] }); });
afterEach(() => { cleanup(); vi.useRealTimers(); vi.unstubAllGlobals(); });

test.each<[AnalystLocale, AnalystStyle]>([["en", "coach"], ["zh", "roast"], ["en", "roast"], ["zh", "coach"]])(
  "automatically generates the missing %s/%s task report once and polls to completion (ready defaults to true)",
  async (locale, style) => {
    const fetcher = install(waiting, queued, running, completed);
    const { result, rerender } = renderHook(() => useReport({ ...task }, locale, style));
    await settle();
    expect(posts()).toHaveLength(1);
    expect(fetcher.mock.calls[0]).toEqual([
      `/api/v1/tasks/training%201/analyst/report?locale=${locale}&style=${style}`,
      expect.objectContaining({ credentials: "include", signal: expect.any(AbortSignal) }),
    ]);
    expect(posts()[0]).toEqual([
      "/api/v1/tasks/training%201/analyst/report",
      expect.objectContaining({ method: "POST", body: JSON.stringify({ locale, style, regenerate: false }), signal: expect.any(AbortSignal) }),
    ]);
    expect(result.current.state?.status).toBe("queued");
    rerender();
    await advance();
    expect(result.current.state?.status).toBe("running");
    await advance();
    expect(result.current.state).toEqual(completed);
    await advance(60_000);
    expect(fetcher).toHaveBeenCalledTimes(4);
    expect(posts()).toHaveLength(1);
    expect(result.current).toMatchObject({ busy: false, error: false });
  },
);

test.each([completed, failed, disabled])("does not auto-generate a $status report", async state => {
  const fetcher = install(state);
  const { result, rerender } = renderHook(() => useReport(task, "en", "roast", true));
  await settle();
  rerender();
  await advance(60_000);
  expect(result.current.state).toEqual(state);
  expect(fetcher).toHaveBeenCalledTimes(1);
  expect(posts()).toHaveLength(0);
});

test.each([queued, running])("polls an existing $status report without posting", async state => {
  const fetcher = install(state, completed);
  const { result } = renderHook(() => useReport(task, "en", "roast"));
  await settle();
  await advance();
  expect(result.current.state).toEqual(completed);
  expect(fetcher).toHaveBeenCalledTimes(2);
  expect(posts()).toHaveLength(0);
});

test.each([waiting, completed, failed, disabled, queued, running])("keeps a $status preset read only, even on explicit generate or reload", async state => {
  install(state, state.status === "queued" || state.status === "running" ? completed : state, waiting);
  const { result } = renderHook(() => useReport({ kind: "preset", id: "demo" }, "en", "roast"));
  await settle();
  await act(async () => { await result.current.generate(); });
  await advance();
  act(() => result.current.reload());
  await settle();
  await act(async () => { await result.current.generate(); });
  await advance(60_000);
  expect(posts()).toHaveLength(0);
  expect(vi.mocked(fetch).mock.calls.every(([url]) => String(url).startsWith("/api/v1/presets/demo/analyst/report?"))).toBe(true);
});

test("blocks automatic and explicit POST until ready changes to true, then reloads", async () => {
  const fetcher = install(waiting, waiting, queued, completed);
  const { result, rerender } = renderHook(({ ready }) => useReport(task, "en", "roast", ready), { initialProps: { ready: false } });
  await settle();
  expect(result.current.state).toEqual(waiting);
  await act(async () => { await result.current.generate(); });
  await advance(60_000);
  expect(posts()).toHaveLength(0);
  expect(fetcher).toHaveBeenCalledTimes(1);
  rerender({ ready: true });
  await settle();
  expect(fetcher).toHaveBeenCalledTimes(3);
  expect(posts()).toHaveLength(1);
  await advance();
  expect(result.current.state).toEqual(completed);
});

test.each([waiting, failed, disabled, completed])("stops on a $status POST response without a GET/POST loop", async state => {
  const fetcher = install(waiting, state);
  const { result, rerender } = renderHook(() => useReport(task, "en", "roast"));
  await settle();
  expect(posts()).toHaveLength(1);
  expect(result.current.state).toEqual(state);
  rerender();
  await advance(60_000);
  expect(fetcher).toHaveBeenCalledTimes(2);
  expect(result.current).toMatchObject({ busy: false, error: false });
});

test.each([waiting, failed, disabled])("stops when polling returns $status after generation", async state => {
  const fetcher = install(waiting, queued, state);
  const { result } = renderHook(() => useReport(task, "en", "roast"));
  await settle();
  await advance();
  expect(result.current.state).toEqual(state);
  await advance(60_000);
  expect(fetcher).toHaveBeenCalledTimes(3);
  expect(posts()).toHaveLength(1);
});

test("requires explicit generation to retry a failed report and preserves regeneration for completed reports", async () => {
  const fetcher = install(failed, completed, completed);
  const { result } = renderHook(() => useReport(task, "en", "roast"));
  await settle();
  await advance(60_000);
  expect(fetcher).toHaveBeenCalledTimes(1);
  await act(async () => { await result.current.generate(); });
  expect(result.current.state).toEqual(completed);
  expect(JSON.parse(String(posts()[0]?.[1]?.body))).toEqual({ locale: "en", style: "roast", regenerate: false });
  await act(async () => { await result.current.generate(); });
  expect(JSON.parse(String(posts()[1]?.[1]?.body))).toEqual({ locale: "en", style: "roast", regenerate: true });
});

test.each([429, 503])("stops after POST HTTP %s and retries only on explicit reload", async status => {
  const fetcher = install(waiting, json({ detail: "Unavailable" }, status), waiting, completed);
  const { result, rerender } = renderHook(() => useReport(task, "en", "roast"));
  await settle();
  expect(result.current).toMatchObject({ error: true, busy: false });
  rerender();
  await advance(60_000);
  expect(fetcher).toHaveBeenCalledTimes(2);
  act(() => result.current.reload());
  await settle();
  expect(result.current).toMatchObject({ state: completed, error: false, busy: false });
  expect(posts()).toHaveLength(2);
});

test("does not generate after a failed GET", async () => {
  const fetcher = install(json({ detail: "Unavailable" }, 503));
  const { result } = renderHook(() => useReport(task, "en", "roast"));
  await settle();
  await advance(60_000);
  expect(result.current.error).toBe(true);
  expect(fetcher).toHaveBeenCalledTimes(1);
  expect(posts()).toHaveLength(0);
});

test("deduplicates explicit calls while automatic generation is pending", async () => {
  const pending = deferredResponse();
  install(waiting, pending.promise, completed);
  const { result, rerender } = renderHook(() => useReport(task, "en", "roast"));
  await settle();
  expect(result.current.busy).toBe(true);
  rerender();
  act(() => { void result.current.generate(); void result.current.generate(); });
  expect(posts()).toHaveLength(1);
  await act(async () => { pending.resolve(json(queued)); });
  expect(result.current.busy).toBe(false);
  await advance();
  expect(result.current.state).toEqual(completed);
});

test("deduplicates synchronous explicit retries before React renders busy", async () => {
  const pending = deferredResponse();
  install(failed, pending.promise);
  const { result } = renderHook(() => useReport(task, "en", "roast"));
  await settle();
  act(() => { void result.current.generate(); void result.current.generate(); });
  expect(posts()).toHaveLength(1);
  await act(async () => { pending.resolve(json(completed)); });
  expect(result.current).toMatchObject({ state: completed, busy: false, error: false });
});

test.each(["GET", "POST"])("aborts an in-flight %s on selection change and ignores a late response", async method => {
  const pending = deferredResponse();
  const fetcher = install(...(method === "GET" ? [pending.promise] : [failed, pending.promise]), completed);
  const initialProps: { source: AnalystSource; locale: AnalystLocale; style: AnalystStyle } = { source: task, locale: "en", style: "roast" };
  const { result, rerender } = renderHook(({ source, locale, style }) => useReport(source, locale, style), { initialProps });
  await settle();
  if (method === "POST") act(() => { void result.current.generate(); });
  const signal = fetcher.mock.calls.at(-1)![1]!.signal!;
  rerender({ source: { kind: "task", id: "next" }, locale: "zh", style: "coach" });
  expect(signal.aborted).toBe(true);
  await settle();
  expect(result.current).toMatchObject({ state: completed, busy: false, error: false });
  // Deliberately resolve despite abort to exercise stale-response protection.
  await act(async () => { pending.resolve(json(method === "GET" ? waiting : queued)); });
  await advance(60_000);
  expect(result.current).toMatchObject({ state: completed, busy: false, error: false });
  expect(fetcher.mock.calls.at(-1)![0]).toBe("/api/v1/tasks/next/analyst/report?locale=zh&style=coach");
});

test.each(["locale", "style"] as const)("aborts automatic generation on %s change and loads the selected report", async field => {
  const pending = deferredResponse();
  const fetcher = install(waiting, pending.promise, waiting, completed);
  const initialProps: { locale: AnalystLocale; style: AnalystStyle } = { locale: "en", style: "roast" };
  const { result, rerender } = renderHook(({ locale, style }) => useReport(task, locale, style), { initialProps });
  await settle();
  expect(posts()).toHaveLength(1);
  const signal = posts()[0][1]!.signal!;
  const selection = { ...initialProps, [field]: field === "locale" ? "zh" : "coach" };
  rerender(selection);
  expect(signal.aborted).toBe(true);
  await settle();
  expect(JSON.parse(String(posts()[1]?.[1]?.body))).toEqual({ ...selection, regenerate: false });
  await act(async () => { pending.resolve(json(failed)); });
  await advance(60_000);
  expect(result.current).toMatchObject({ state: completed, busy: false, error: false });
  expect(fetcher).toHaveBeenCalledTimes(4);
});

test("aborts pending generation when ready becomes false and allows a new selection to load", async () => {
  const pending = deferredResponse();
  install(waiting, pending.promise, waiting);
  const { result, rerender } = renderHook(({ ready }) => useReport(task, "en", "roast", ready), { initialProps: { ready: true } });
  await settle();
  expect(posts()).toHaveLength(1);
  const signal = posts()[0][1]!.signal!;
  rerender({ ready: false });
  expect(signal.aborted).toBe(true);
  await settle();
  await act(async () => { pending.resolve(json(queued)); await result.current.generate(); });
  await advance(60_000);
  expect(result.current).toMatchObject({ state: waiting, busy: false, error: false });
  expect(posts()).toHaveLength(1);
});

test("reload cancels pending POST immediately and ignores its late response", async () => {
  const pending = deferredResponse();
  install(failed, pending.promise, completed);
  const { result } = renderHook(() => useReport(task, "en", "roast"));
  await settle();
  act(() => { void result.current.generate(); });
  const signal = posts()[0][1]!.signal!;
  act(() => result.current.reload());
  expect(signal.aborted).toBe(true);
  await settle();
  await act(async () => { pending.resolve(json(queued)); });
  await advance(60_000);
  expect(result.current).toMatchObject({ state: completed, busy: false, error: false });
  expect(posts()).toHaveLength(1);
});

test.each(["GET", "POST", "poll"])("unmount cancels %s work and prevents further requests", async phase => {
  const pending = deferredResponse();
  const fetcher = install(...(phase === "GET" ? [pending.promise] : phase === "POST" ? [waiting, pending.promise] : [waiting, queued]));
  const { unmount } = renderHook(() => useReport(task, "en", "roast"));
  await settle();
  if (phase !== "GET") expect(posts()).toHaveLength(1);
  const signal = fetcher.mock.calls.at(-1)![1]!.signal!;
  const count = fetcher.mock.calls.length;
  unmount();
  expect(signal.aborted).toBe(true);
  await act(async () => { pending.resolve(json(phase === "GET" ? waiting : queued)); });
  await advance(60_000);
  expect(fetcher).toHaveBeenCalledTimes(count);
});

test("StrictMode effect replay does not double POST", async () => {
  const fetcher = install(waiting, waiting, completed);
  const { result } = renderHook(() => useReport(task, "en", "roast"), { wrapper: StrictMode });
  await settle();
  expect(fetcher.mock.calls[0][1]!.signal!.aborted).toBe(true);
  expect(posts()).toHaveLength(1);
  expect(result.current.state).toEqual(completed);
});
