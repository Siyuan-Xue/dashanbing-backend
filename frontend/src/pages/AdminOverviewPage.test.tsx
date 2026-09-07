import { render, screen, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, expect, test, vi } from "vitest";
import { LocaleProvider } from "../providers/LocaleProvider";
import { AdminOverviewPage } from "./AdminOverviewPage";

const overview = {
  resources: { cpu: { logical_count: 4, load_average: null }, memory: null, disk: null, gpu: null },
  queues: { video: { queued: 0, running: 0, failed: 2, completed: 9 }, ai: { queued: 0, running: 0, failed: 1, completed: 0 }, preset: { queued: 0, running: 0, failed: 0, completed: 0 } },
  usage: { ai_attempts: 0, ai_tokens: 0, video_submissions: 0 }, users: { total: 1, active: 1 },
  repair_budget: { utc_date: "2026-09-07", video_used: 0, video_limit: 20, ai_used: 0, ai_limit: 100 },
};
function view(patch = {}) {
  vi.stubGlobal("fetch", vi.fn(async () => Response.json({ ...overview, ...patch })));
  render(<MemoryRouter><LocaleProvider><AdminOverviewPage/></LocaleProvider></MemoryRouter>);
}
beforeEach(() => localStorage.setItem("dashanbing-locale", "en"));

test("overview displays server sample counts and second percentiles, preserving zero and unavailable", async () => {
  view({ timings: { video_queue_seconds: { count: 12, p50: 1.25, p95: 8.5 }, video_execution_seconds: { count: 9, p50: 0, p95: 20 }, ai_total_seconds: { count: 0, p50: null, p95: null } }, errors: [{ kind: "video", code: "engine_failed", count: 2 }, { kind: "ai", code: "generation_failed", count: 1 }] });
  const timing = await screen.findByRole("region", { name: "Timing summary (seconds)" });
  const queue = within(timing).getByRole("row", { name: /Video queue/ });
  expect(within(queue).getAllByRole("cell").map(cell => cell.textContent)).toEqual(["Video queue", "12", "1.25", "8.5"]);
  const execution = within(timing).getByRole("row", { name: /Video execution/ });
  expect(within(execution).getAllByRole("cell").map(cell => cell.textContent)).toEqual(["Video execution", "9", "0", "20"]);
  const ai = within(timing).getByRole("row", { name: /AI total/ });
  expect(within(ai).getAllByRole("cell").map(cell => cell.textContent)).toEqual(["AI total", "0", "Unavailable", "Unavailable"]);
  const errors = screen.getByRole("region", { name: "Error categories" });
  expect(within(errors).getByRole("row", { name: /Video.*Engine failure.*engine_failed.*2/i })).toBeVisible();
  expect(within(errors).getByRole("row", { name: /AI.*Generation failed.*generation_failed.*1/i })).toBeVisible();
});
test("older overview responses show unavailable summaries instead of invented zeros or no-error claims", async () => {
  view();
  const timing = await screen.findByRole("region", { name: "Timing summary (seconds)" });
  expect(within(timing).getAllByText("Unavailable")).toHaveLength(9);
  expect(screen.getByRole("region", { name: "Error categories" })).toHaveTextContent("Unavailable");
  expect(screen.queryByText("No recorded errors")).not.toBeInTheDocument();
});
test("Chinese error summary distinguishes an empty recorded list from missing telemetry", async () => {
  localStorage.setItem("dashanbing-locale", "zh"); view({ errors: [] });
  expect(await screen.findByRole("region", { name: "错误分类" })).toHaveTextContent("暂无已记录错误");
  expect(screen.getByRole("region", { name: "耗时概况（秒）" })).toBeVisible();
});
