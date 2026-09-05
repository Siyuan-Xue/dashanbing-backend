import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, expect, test, vi } from "vitest";
import App from "../App";
const json = (data: unknown) => new Response(JSON.stringify(data), { headers: { "Content-Type": "application/json" } });
const profiles = [
  { id: "p1", kind: "player", name: "Alex", goals: "Balance", notes: "Left-handed", created_at: "2026-09-05", updated_at: "2026-09-05" },
  { id: "p2", kind: "team", name: "Second team", goals: "Teamwork", notes: "", created_at: "2026-09-05", updated_at: "2026-09-05" },
];
beforeEach(() => {
  localStorage.setItem("dashanbing-locale", "en");
  vi.stubGlobal("fetch", vi.fn(async (input: string) => {
    const url = new URL(input, "http://localhost");
    if (url.pathname.endsWith("/users/me")) return json({ id: 7, username: "coach", email: "coach@example.com", is_active: true });
    if (url.pathname.endsWith("/training-profiles")) return json(profiles);
    if (url.pathname.endsWith("/history")) return json([]);
    if (url.pathname.endsWith("/tasks")) return json({ items: [], total: 0 });
    return json([]);
  }));
});

test("opens the profile from its URL and shows actionable empty history", async () => {
  render(<MemoryRouter initialEntries={["/workspace/profiles/p2"]}><App/></MemoryRouter>);
  expect(await screen.findByRole("heading", { name: "Second team" })).toBeVisible();
  expect(screen.queryByRole("heading", { name: "Alex" })).not.toBeInTheDocument();
  const empty = (await screen.findByRole("heading", { name: "No training history yet" })).closest(".workspace-state")!;
  expect(within(empty as HTMLElement).getByRole("link", { name: "View tasks" })).toHaveAttribute("href", "/workspace/tasks");
  await userEvent.setup().click(screen.getByRole("link", { name: "Back to profiles" }));
  expect(await screen.findByRole("table")).toBeVisible();
});

test("unknown profile IDs show not found instead of silently selecting the first profile", async () => {
  render(<MemoryRouter initialEntries={["/workspace/profiles/missing"]}><App/></MemoryRouter>);
  expect(await screen.findByRole("heading", { name: "Profile not found" })).toBeVisible();
  expect(screen.queryByText("Balance")).not.toBeInTheDocument();
  expect(screen.getByRole("link", { name: "Back to profiles" })).toHaveAttribute("href", "/workspace/profiles");
});
