import { act, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, expect, test, vi } from "vitest";
import { LocaleProvider } from "../providers/LocaleProvider";
import { ComparisonReports } from "./ComparisonReports";
import type { AnalystContext, ComparisonReportState } from "./types";

const context = { task_id: "t1", facts: { evidence: [{ id: "ev1", time_ms: 1000, times_ms: { phases: 1000 }, media_kind: "phases" }] }, subjects: [{ id: "s1", label: "Player 1", profile_id: "p1" }], team_profile_id: null, comparison_id: null, comparisons: [{ id: "old1", profile_id: "p1", occurred_at: "2026-09-01", mode: "quick", metrics: {}, media_available: true }, { id: "old2", profile_id: "p1", occurred_at: "2026-08-28", mode: "quick", metrics: {}, media_available: false }] } as unknown as AnalystContext;
const complete: ComparisonReportState = { comparison_id: "old1", status: "completed", error: null, report: { id: "comparison1", summary: "Compare the same recorded drill", highlights: [{ text: "This release", evidence_ids: ["ev1"] }], comparison: { text: "Two comparable sessions", evidence_ids: [] }, suggestions: ["Repeat this drill"], players: [], model: "glm-5.3", style: "coach", locale: "en", created_at: "2026-09-05" } };
const writes = () => vi.mocked(fetch).mock.calls.filter(([, init]) => init?.method === "POST");
const ui = (value = context) => <LocaleProvider><p>Original analysis</p><ComparisonReports source={{ kind: "task", id: "t1" }} context={value} style="coach" disabled={false} onEvidence={() => {}}/></LocaleProvider>;
beforeEach(() => {
  localStorage.setItem("dashanbing-locale", "en");
  vi.stubGlobal("fetch", vi.fn(async (url: string, init?: RequestInit) => url.includes("training-profiles") ? Response.json([{ id: "p1", kind: "player", name: "Alex" }]) : init?.method === "POST" ? Response.json(complete) : Response.json({ items: [] })));
});
test("never generates automatically, and needs confirmed profiles with comparable history", async () => {
  render(ui({ ...context, subjects: [{ id: "s1", label: "Player 1", profile_id: null }], comparisons: [] }));
  await waitFor(() => expect(fetch).toHaveBeenCalled());
  expect(screen.queryByRole("button", { name: "Compare training" })).not.toBeInTheDocument();
  expect(writes()).toHaveLength(0);
});
test("selecting history is a draft, explicit generation appends a report without modifying context", async () => {
  const user = userEvent.setup(); render(ui());
  await user.click(screen.getByRole("button", { name: "Compare training" }));
  await user.selectOptions(screen.getByLabelText("Historical session"), "old1");
  expect(writes()).toHaveLength(0);
  expect(await screen.findAllByRole("option", { name: /Alex/ })).toHaveLength(2);
  await user.click(screen.getByRole("button", { name: "Generate comparison" }));
  expect(await screen.findByText("Compare the same recorded drill")).toBeVisible();
  expect(screen.getByText("Original analysis")).toBeVisible();
  expect(writes()).toHaveLength(1);
  expect(JSON.parse(String(writes()[0][1]?.body))).toEqual({ comparison_id: "old1", locale: "en", style: "coach" });
  expect(vi.mocked(fetch).mock.calls.some(([url]) => String(url).endsWith("/context"))).toBe(false);
});
test("Escape cancels the picker without posting or changing the original", async () => {
  const user = userEvent.setup(); render(ui());
  const trigger = screen.getByRole("button", { name: "Compare training" });
  await user.click(trigger); await user.selectOptions(screen.getByLabelText("Historical session"), "old2");
  await user.keyboard("{Escape}");
  expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  expect(trigger).toHaveFocus(); expect(writes()).toHaveLength(0);
});
test("previous comparison reports restore by reading and do not generate again", async () => {
  vi.stubGlobal("fetch", vi.fn(async () => Response.json({ items: [complete] })));
  render(ui());
  expect(await screen.findByText("Two comparable sessions")).toBeVisible();
  expect(writes()).toHaveLength(0);
});
test("failed requests preserve the original and allow an explicit retry", async () => {
  let fail = true;
  vi.stubGlobal("fetch", vi.fn(async (url: string, init?: RequestInit) => url.includes("training-profiles") ? Response.json([]) : init?.method === "POST" ? fail ? Response.json({ detail: "Unavailable" }, { status: 503 }) : Response.json(complete) : Response.json({ items: [] })));
  const user = userEvent.setup(); render(ui());
  await user.click(screen.getByRole("button", { name: "Compare training" }));
  await user.click(screen.getByRole("button", { name: "Generate comparison" }));
  expect(await screen.findByRole("alert")).toBeVisible();
  expect(screen.getByText("Original analysis")).toBeVisible();
  fail = false;
  await user.click(screen.getByRole("button", { name: "Generate comparison" }));
  expect(await screen.findByText("Two comparable sessions")).toBeVisible();
  expect(writes()).toHaveLength(2);
});
test("prevents repeated submits and ignores a late response after leaving the task", async () => {
  let finish!: (response: Response) => void;
  vi.stubGlobal("fetch", vi.fn(async (url: string, init?: RequestInit) => init?.method === "POST" ? new Promise<Response>(resolve => { finish = resolve; }) : url.includes("training-profiles") ? Response.json([]) : Response.json({ items: [] })));
  const user = userEvent.setup(); const view = render(ui());
  await user.click(screen.getByRole("button", { name: "Compare training" }));
  const submit = screen.getByRole("button", { name: "Generate comparison" });
  act(() => { submit.click(); submit.click(); });
  expect(writes()).toHaveLength(1);
  view.unmount();
  await act(async () => finish(Response.json(complete)));
  expect(screen.queryByText("Two comparable sessions")).not.toBeInTheDocument();
});
test("queued comparison polls to completion without posting again", async () => {
  vi.useFakeTimers({ shouldAdvanceTime: true });
  let requested = false;
  vi.stubGlobal("fetch", vi.fn(async (url: string, init?: RequestInit) => {
    if (init?.method === "POST") { requested = true; return Response.json({ comparison_id: "old1", status: "queued", report: null, error: null }); }
    if (url.includes("training-profiles")) return Response.json([]);
    return Response.json({ items: requested ? [complete] : [] });
  }));
  try {
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime }); render(ui());
    await user.click(screen.getByRole("button", { name: "Compare training" }));
    await user.click(screen.getByRole("button", { name: "Generate comparison" }));
    expect(await screen.findByText("Analysis queued")).toBeVisible();
    await act(async () => vi.advanceTimersByTimeAsync(2100));
    expect(await screen.findByText("Two comparable sessions")).toBeVisible();
    expect(writes()).toHaveLength(1);
  } finally { vi.useRealTimers(); }
});

test("failed comparison retries stay inside the top picker without adding toolbar buttons", async () => {
  vi.stubGlobal("fetch", vi.fn(async () => Response.json({ items: [{ ...complete, status: "failed", report: null }] })));
  const user = userEvent.setup(); render(ui());
  await screen.findByText("Analysis failed");
  expect(screen.queryByRole("button", { name: "Retry comparison" })).not.toBeInTheDocument();
  await user.click(screen.getByRole("button", { name: "Compare training" }));
  expect(within(screen.getByRole("dialog")).getByRole("button", { name: /Retry comparison/ })).toBeVisible();
});
