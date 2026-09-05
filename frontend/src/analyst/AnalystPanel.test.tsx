import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, expect, test, vi } from "vitest";
import { LocaleProvider } from "../providers/LocaleProvider";
import { ResultWorkspace } from "../components/ResultWorkspace";
import { AnalystPanel } from "./AnalystPanel";
import type { AnalystContext, ReportState } from "./types";
import type { ProductResult } from "../workspace/types";

export const context: AnalystContext = { task_id: "t1", facts: { schema_version: 1, metrics: { action_counts: { jump_shot: 1 }, shots: { attempts: 1, makes: 1 }, registered_participant_count: 1, event_count: 1 }, subjects: [{ id: "s1", label: "Player 1" }], evidence: [{ id: "ev1", event_index: 0, subject_id: "s1", action_type: "jump_shot", start_ms: 1000, end_ms: 3000, time_ms: 2000, media_kind: "phases", times_ms: { phases: 2000, cam_02: 23500 }, result: "make", confidence: null, angles: {} }], warnings: [], pose_available: false }, subjects: [{ id: "s1", label: "Player 1", profile_id: null }], team_profile_id: null, comparison_id: null, comparisons: [] };
export const completed: ReportState = { status: "completed", report: { id: "r1", summary: "Your recorded shot went in", highlights: [{ text: "Review the release", evidence_ids: ["ev1", "missing"] }], players: [], comparison: null, suggestions: ["Practice the same release"], model: "gpt-real", locale: "en", style: "coach", created_at: "2026-09-05T01:00:00Z" }, error: null };
const json = (data: unknown, status = 200) => new Response(JSON.stringify(data), { status, headers: { "Content-Type": "application/json" } });
function install(report: ReportState = completed) {
  vi.stubGlobal("fetch", vi.fn(async (input: string, init?: RequestInit) => {
    if (input.endsWith("/context")) return json(context);
    if (input === "/api/v1/training-profiles") return json([]);
    if (input.includes("/report")) return json(report);
    throw new Error(`Unknown route ${init?.method || "GET"} ${input}`);
  }));
}
beforeEach(() => { localStorage.setItem("dashanbing-locale", "en"); sessionStorage.clear(); });

test("settings are dismissible while the analyst report always stays visible", async () => {
  install();
  const user = userEvent.setup();
  render(<LocaleProvider><AnalystPanel source={{ kind: "task", id: "t1" }} onEvidence={() => {}}/></LocaleProvider>);
  const summary = await screen.findByText("Your recorded shot went in");
  const trigger = screen.getByRole("button", { name: "Configure" });
  expect(screen.queryByRole("dialog", { name: "Configure" })).not.toBeInTheDocument();
  expect(screen.queryByRole("button", { name: /Collapse AI/ })).not.toBeInTheDocument();
  await user.click(trigger);
  expect(screen.getByRole("dialog", { name: "Configure" })).toBeVisible();
  expect(screen.getByLabelText("Current player")).toHaveFocus();
  await user.keyboard("{Escape}");
  expect(trigger).toHaveFocus();
  expect(summary).toBeVisible();
  await user.click(trigger);
  await user.click(summary);
  expect(trigger).toHaveAttribute("aria-expanded", "false");
  expect(summary).toBeVisible();
});

test("unknown analyst routes show a recoverable state without breaking other result views", async () => {
  vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new Error("Unknown API")));
  render(<LocaleProvider><AnalystPanel source={{ kind: "task", id: "t1" }} onEvidence={() => {}}/></LocaleProvider>);
  expect(await screen.findByText("AI analyst unavailable")).toBeVisible();
  expect(screen.getByRole("button", { name: "Retry analyst" })).toBeEnabled();
});

test("preset reports are read only, use known citations and never offer profile linking or generation", async () => {
  install({ ...completed, facts: context.facts, subjects: context.subjects });
  const seek = vi.fn(); const user = userEvent.setup();
  render(<LocaleProvider><AnalystPanel source={{ kind: "preset", id: "quick-demo" }} onEvidence={seek}/></LocaleProvider>);
  expect(await screen.findByText("Your recorded shot went in")).toBeVisible();
  expect(screen.queryByRole("button", { name: "Generate report" })).not.toBeInTheDocument();
  expect(screen.queryByLabelText("Link player profile")).not.toBeInTheDocument();
  expect(screen.queryByRole("button", { name: /missing/ })).not.toBeInTheDocument();
  await user.click(screen.getByRole("button", { name: /View evidence.*2.0/ }));
  expect(seek).toHaveBeenCalledWith(context.facts.evidence[0]);
});

test("disabled service shows truthful status and prevents chat and report requests", async () => {
  install({ status: "disabled", report: null, error: null });
  render(<LocaleProvider><AnalystPanel source={{ kind: "task", id: "t1" }} onEvidence={() => {}}/></LocaleProvider>);
  expect(await screen.findByText("AI is not configured")).toBeVisible();
  expect(screen.getByRole("textbox", { name: "Ask the analyst" })).toBeDisabled();
  expect(screen.queryByRole("button", { name: "Generate report" })).not.toBeInTheDocument();
});

test("evidence seeks the active camera's own time, including before metadata and on camera switch", async () => {
  install();
  const scroll = vi.fn(); Element.prototype.scrollIntoView = scroll;
  const result = { media: { phases: "/phases.mp4", cam_02: "/cam2.mp4" }, shots: { attempts: 1, makes: 1, make_rate: 1 }, events: [], registered_participant_count: 1, action_counts: {}, warnings: [], disclaimer: "" } as unknown as ProductResult;
  const user = userEvent.setup();
  render(<LocaleProvider><ResultWorkspace result={result} analystSource={{ kind: "task", id: "t1" }}/></LocaleProvider>);
  await user.click(screen.getByRole("tab", { name: "Camera 2" }));
  await user.click(await screen.findByRole("button", { name: /View evidence.*2.0/ }));
  const camera = screen.getByTitle("Camera 2 player") as HTMLVideoElement;
  fireEvent.loadedMetadata(camera);
  expect(camera.currentTime).toBe(23.5);
  expect(scroll).toHaveBeenCalled();
  await user.click(screen.getByRole("tab", { name: "Phase mosaic" }));
  const phases = screen.getByTitle("Phase mosaic player") as HTMLVideoElement;
  fireEvent.loadedMetadata(phases);
  expect(phases.currentTime).toBe(2);
  const sections = document.querySelector(".result-workspace")!.children;
  expect(sections[0]).toHaveClass("result-media-panel");
  expect(sections[1]).toHaveClass("result-insights-panel");
  expect(sections[2]).toHaveAttribute("id", "analyst");
  expect(within(sections[2] as HTMLElement).getByRole("button", { name: "Configure" })).toHaveAttribute("aria-expanded", "false");
});

test("context association submits all subjects and clears comparison when the team changes", async () => {
  install();
  const fetcher = vi.mocked(fetch); const base = fetcher.getMockImplementation()!;
  fetcher.mockImplementation(async (input, init) => {
    if (String(input) === "/api/v1/training-profiles") return json([{ id: "p1", kind: "player", name: "Alex", goals: "", notes: "" }, { id: "team1", kind: "team", name: "Team A", goals: "", notes: "" }]);
    if (String(input).endsWith("/context") && init?.method === "PUT") return json({ ...context, ...JSON.parse(String(init.body)), subjects: JSON.parse(String(init.body)).subjects.map((subject: { id: string }) => ({ ...context.subjects.find(value => value.id === subject.id), ...subject })) });
    return base(input, init);
  });
  const user = userEvent.setup();
  render(<LocaleProvider><AnalystPanel source={{ kind: "task", id: "t1" }} onEvidence={() => {}}/></LocaleProvider>);
  await user.click(screen.getByRole("button", { name: "Configure" }));
  await user.selectOptions(await screen.findByLabelText("Current player"), "s1");
  await user.selectOptions(screen.getByLabelText("Link player profile"), "p1");
  await waitFor(() => expect(fetcher).toHaveBeenCalledWith("/api/v1/tasks/t1/analyst/context", expect.objectContaining({ method: "PUT", body: JSON.stringify({ subjects: [{ id: "s1", profile_id: "p1" }], team_profile_id: null, comparison_id: null }) })));
  await waitFor(() => expect(screen.getByLabelText("Team profile")).toBeEnabled());
  await user.selectOptions(screen.getByLabelText("Team profile"), "team1");
  await waitFor(() => expect(fetcher).toHaveBeenCalledWith("/api/v1/tasks/t1/analyst/context", expect.objectContaining({ body: JSON.stringify({ subjects: [{ id: "s1", profile_id: "p1" }], team_profile_id: "team1", comparison_id: null }) })));
});

test("tasks without a completed result cannot chat while a completed result can chat before its report exists", async () => {
  install({ status: "waiting", report: null, error: null });
  const result = { media: {}, shots: { attempts: 0, makes: 0 }, events: [], action_counts: {}, registered_participant_count: 0, warnings: [], disclaimer: "" } as unknown as ProductResult;
  const rendered = render(<LocaleProvider><ResultWorkspace result={null} analystSource={{ kind: "task", id: "t1" }}/></LocaleProvider>);
  await screen.findByText("Report not generated yet");
  expect(screen.getByRole("textbox", { name: "Ask the analyst" })).toBeDisabled();
  expect(screen.queryByRole("button", { name: "Generate report" })).not.toBeInTheDocument();
  rendered.rerender(<LocaleProvider><ResultWorkspace result={result} analystSource={{ kind: "task", id: "t1" }}/></LocaleProvider>);
  expect(screen.getByRole("textbox", { name: "Ask the analyst" })).toBeEnabled();
});

test("localizes backend-generated subject labels without changing subject ids", async () => {
  install({ ...completed, facts: context.facts, subjects: [{ id: "s1", label: "球员 1" }] });
  render(<LocaleProvider><AnalystPanel source={{ kind: "preset", id: "quick-demo" }} onEvidence={() => {}}/></LocaleProvider>);
  await userEvent.click(screen.getByRole("button", { name: "Configure" }));
  expect(await screen.findByRole("option", { name: "Player 1" })).toHaveValue("s1");
});

test("a personal scope keeps the full summary but hides another profile's comparison and omits it from chat", async () => {
  const teamHistory = { id: "team-history", profile_id: "team1", task_id: null, occurred_at: "2026-09-01", mode: "quick", metrics: {}, media_available: false };
  vi.stubGlobal("fetch", vi.fn(async (input: string, init?: RequestInit) => {
    if (input.endsWith("/context")) return json(init?.method === "PUT" ? { ...context, team_profile_id: "team1", comparison_id: teamHistory.id, comparisons: [teamHistory] } : context);
    if (input === "/api/v1/training-profiles") return json([{ id: "team1", kind: "team", name: "Team A" }]);
    if (input.includes("/report")) return json({ ...completed, report: { ...completed.report, comparison: { text: "Full team baseline", evidence_ids: [] } } });
    return json({ detail: "Test stops before posting a message" }, 503);
  }));
  const user = userEvent.setup();
  render(<LocaleProvider><AnalystPanel source={{ kind: "task", id: "t1" }} onEvidence={() => {}}/></LocaleProvider>);
  expect(await screen.findByText("Full team baseline")).toBeVisible();
  await user.click(screen.getByRole("button", { name: "Configure" }));
  await user.selectOptions(await screen.findByLabelText("Current player"), "s1");
  // First linking can return an automatic global team baseline even in a personal scope.
  await user.selectOptions(screen.getByLabelText("Team profile"), "team1");
  await waitFor(() => expect(screen.getByLabelText("Team profile")).toBeEnabled());
  expect(screen.getByText("Your recorded shot went in")).toBeVisible();
  expect(screen.queryByText("Full team baseline")).not.toBeInTheDocument();
  expect(within(screen.getByLabelText("Compare with")).queryByRole("option", { name: /Team A/ })).not.toBeInTheDocument();
  await user.type(screen.getByLabelText("Ask the analyst"), "My next practice?");
  await user.click(screen.getByRole("button", { name: "Send" }));
  await waitFor(() => expect(fetch).toHaveBeenCalledWith("/api/v1/analyst/conversations", expect.objectContaining({ method: "POST", body: JSON.stringify({ task_id: "t1", subject_id: "s1", locale: "en", style: "coach" }) })));
});
