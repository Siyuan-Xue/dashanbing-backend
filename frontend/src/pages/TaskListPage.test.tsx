import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, expect, test, vi } from "vitest";
import { LocaleProvider } from "../providers/LocaleProvider";
import { TaskListPage } from "./TaskListPage";
const json = (data: unknown) => new Response(JSON.stringify(data), { headers: { "Content-Type": "application/json" } });
const view = (path = "/workspace/tasks") => render(<MemoryRouter initialEntries={[path]}><LocaleProvider><TaskListPage/></LocaleProvider></MemoryRouter>);
beforeEach(() => localStorage.setItem("dashanbing-locale", "en"));

test("empty tasks explain the next step and link to creation", async () => {
  vi.stubGlobal("fetch", vi.fn(async () => json({ items: [], total: 0 })));
  view();
  expect(await screen.findByRole("heading", { name: "No tasks yet" })).toBeVisible();
  expect(screen.getByRole("link", { name: "Create task" })).toHaveAttribute("href", "/workspace/new");
});

test("clearing no-match filters removes search, status and mode and resets the page", async () => {
  const requests: URL[] = [];
  vi.stubGlobal("fetch", vi.fn(async (input: string) => { requests.push(new URL(input, "http://localhost")); return json({ items: [], total: 0 }); }));
  const user = userEvent.setup(); view("/workspace/tasks?q=missing&status=completed&mode=quick&page=3&page_size=20");
  expect(await screen.findByRole("heading", { name: "No matching tasks" })).toBeVisible();
  await user.click(screen.getByRole("button", { name: "Clear filters" }));
  expect(await screen.findByRole("heading", { name: "No tasks yet" })).toBeVisible();
  expect(screen.getByRole("searchbox")).toHaveValue("");
  const params = requests.at(-1)!.searchParams;
  expect(params.get("q")).toBeNull(); expect(params.get("status")).toBeNull(); expect(params.get("mode")).toBeNull();
  expect(params.get("page")).toBe("1"); expect(params.get("page_size")).toBe("20");
});

test("task progress remains inline with its percentage and failed tasks retain open, retry and delete", async () => {
  vi.stubGlobal("fetch", vi.fn(async () => json({ total: 1, items: [{ id: "failed1", title: "Evening practice", status: "failed", progress: 42, mode: "quick", stage_message: "", inputs: [], created_at: "2026-09-05T01:00:00Z" }] })));
  view();
  const progress = await screen.findByRole("progressbar", { name: "Progress · Evening practice" });
  expect(progress).toHaveAttribute("aria-valuenow", "42");
  expect(progress).toHaveTextContent("42%");
  expect(screen.getByRole("link", { name: "Open" })).toHaveAttribute("href", "/workspace/tasks/failed1");
  expect(screen.getByRole("button", { name: /Retry.*Evening practice/ })).toBeEnabled();
  expect(screen.getByRole("button", { name: /Delete.*Evening practice/ })).toBeEnabled();
});
