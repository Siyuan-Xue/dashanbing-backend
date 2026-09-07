import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, expect, test, vi } from "vitest";
import { LocaleProvider } from "../providers/LocaleProvider";
import { AdminPage, type AdminSection } from "./AdminPage";

const quotas = { drafts: 3, unfinished: 5, daily_video: 20, daily_ai: 100 };
const budget = { utc_date: "2026-09-07", video_used: 2, video_limit: 20, ai_used: 4, ai_limit: 100 };
const settings = { current: { video_enabled: true, video_paused: false, ai_enabled: true, ai_paused: false, ai_concurrency: 8, default_quotas: quotas }, bounds: { ai_concurrency: { min: 1, max: 8 }, priority: { min: -100, max: 100 }, quotas: { drafts: { min: 0, max: 30 }, unfinished: { min: 0, max: 50 }, daily_video: { min: 0, max: 200 }, daily_ai: { min: 0, max: 1000 } }, batch_size: 10, admin_retries: 3 }, repair_budget: budget };
const member = { id: 2, username: "member", email: "member@example.test", role: "user", is_active: true, created_at: "2026-09-07T00:00:00Z", quotas, quota_overrides: {}, usage: { drafts: 0, unfinished: 1, daily_video: 2, daily_ai: 3 } };
const job = (id: string, kind = "video") => ({ id, kind, owner_id: 2, task_id: id, status: "queued", created_at: "2026-09-07T00:00:00Z", updated_at: "2026-09-07T00:00:00Z", attempts: 0, held: false, priority: 0, admin_retries: 0, allowed_actions: ["hold", "priority"], report: "private report content" });
const page = (items: unknown[]) => ({ items, total: items.length, page: 1, page_size: 20 });
function view(section: AdminSection) { render(<MemoryRouter><LocaleProvider><AdminPage section={section}/></LocaleProvider></MemoryRouter>); }
function serve(handler: (path: string, init?: RequestInit) => Response | undefined) {
  vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const path = new URL(String(input), "http://localhost").pathname;
    return handler(path, init) || (path.endsWith("/settings") ? Response.json(settings) : Response.json(page([])));
  }));
}
async function confirm(user: ReturnType<typeof userEvent.setup>) { await user.type(screen.getByRole("textbox", { name: "Reason" }), "maintenance window"); await user.click(screen.getByRole("checkbox", { name: /reviewed/ })); await user.click(screen.getByRole("button", { name: "Confirm action" })); }
beforeEach(() => localStorage.setItem("dashanbing-locale", "en"));

test("disabling a user sends the confirmed reason and refreshes actual account status", async () => {
  let active = true; const mutations: unknown[] = [];
  serve((path, init) => {
    if (path.endsWith("/users/2") && init?.method === "PATCH") { mutations.push(JSON.parse(String(init.body))); active = false; return Response.json({ ...member, is_active: false }); }
    if (path.endsWith("/users")) return Response.json(page([{ ...member, is_active: active }]));
  });
  const user = userEvent.setup(); view("users");
  await user.click(await screen.findByRole("button", { name: "Disable account · member" }));
  expect(mutations).toEqual([]); await confirm(user);
  expect(await screen.findByRole("button", { name: "Enable account · member" })).toBeEnabled();
  expect(mutations).toEqual([{ is_active: false, reason: "maintenance window" }]);
});
test("job selection caps at ten and cannot mix kinds; metadata excludes report bodies", async () => {
  serve(path => path.endsWith("/jobs") ? Response.json(page([...Array.from({ length: 11 }, (_, index) => job(`job-${index}`)), job("ai-job", "ai")])) : undefined);
  const user = userEvent.setup(); view("scheduling");
  await screen.findByRole("checkbox", { name: "Select · job-0" });
  for (let index = 0; index < 10; index++) await user.click(screen.getByRole("checkbox", { name: `Select · job-${index}` }));
  expect(screen.getByRole("checkbox", { name: "Select · job-10" })).toBeDisabled();
  expect(screen.getByRole("checkbox", { name: "Select · ai-job" })).toBeDisabled();
  await user.click(screen.getByRole("button", { name: "Metadata · job-0" }));
  expect(screen.getByRole("dialog")).toHaveTextContent("job-0");
  expect(screen.queryByText("private report content")).not.toBeInTheDocument();
});
test("a stale queue action preserves an error without a success notice", async () => {
  const mutations: unknown[] = [];
  serve((path, init) => {
    if (path.endsWith("/jobs/actions")) { mutations.push(JSON.parse(String(init?.body))); return Response.json({ detail: "stale" }, { status: 409 }); }
    if (path.endsWith("/jobs")) return Response.json(page([job("job-1")]));
  });
  const user = userEvent.setup(); view("scheduling");
  await user.click(await screen.findByRole("checkbox", { name: "Select · job-1" }));
  await user.click(screen.getByRole("button", { name: "Hold selected" })); await confirm(user);
  expect(await screen.findByRole("alert")).toHaveTextContent("The state changed");
  expect(mutations).toEqual([{ kind: "video", ids: ["job-1"], action: "hold", reason: "maintenance window" }]);
  expect(screen.queryByText("Action completed")).not.toBeInTheDocument();
});
test("quota fields follow backend bounds and send only changed values", async () => {
  const mutations: unknown[] = [];
  serve((path, init) => { if (path.endsWith("/settings") && init?.method === "PATCH") { mutations.push(JSON.parse(String(init.body))); return Response.json(settings); } });
  const user = userEvent.setup(); view("quotas");
  const field = await screen.findByRole("spinbutton", { name: "AI concurrency" });
  expect(field).toHaveAttribute("max", "8");
  await user.clear(field); await user.type(field, "9");
  expect(screen.getByRole("button", { name: "Save changes" })).toBeDisabled();
  await user.clear(field); await user.type(field, "4");
  await user.click(screen.getByRole("button", { name: "Save changes" })); await confirm(user);
  await waitFor(() => expect(mutations).toEqual([{ ai_concurrency: 4, reason: "maintenance window" }]));
});
test("operations is read only and unavailable telemetry is unknown", async () => {
  serve(path => path.endsWith("/deployment") ? Response.json({ application: { version: "1.0", database_revision: null }, workers: { video_enabled: true, ai_enabled: false }, backup: { status: "unknown" }, read_only: true }) : path.endsWith("/overview") ? Response.json({ resources: { cpu: { logical_count: 8, load_average: null }, memory: null, disk: null, gpu: null }, queues: { video: { queued: 0, running: 0, failed: 0, completed: 0 }, ai: { queued: 0, running: 0, failed: 0, completed: 0 }, preset: { queued: 0, running: 0, failed: 0, completed: 0 } }, usage: { ai_attempts: 0, ai_tokens: 0, video_submissions: 0 }, users: { total: 0, active: 0 }, repair_budget: budget }) : undefined);
  view("operations");
  expect(await screen.findByText("1.0")).toBeVisible();
  expect(screen.getAllByText("Unknown").length).toBeGreaterThan(0);
  expect(screen.getAllByRole("button")).toHaveLength(1);
  expect(screen.getByRole("button", { name: "Refresh" })).toBeEnabled();
});
test("a failed list request displays a centered retry state instead of an empty success", async () => {
  serve(path => path.endsWith("/users") ? Response.json({}, { status: 503 }) : undefined); view("users");
  expect(await screen.findByRole("heading", { name: "Unable to load data" })).toBeVisible();
  expect(screen.getByRole("button", { name: "Retry" })).toBeEnabled();
  expect(screen.queryByRole("heading", { name: "No records" })).not.toBeInTheDocument();
});
