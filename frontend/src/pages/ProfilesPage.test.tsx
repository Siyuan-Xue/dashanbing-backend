import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, expect, test, vi } from "vitest";
import { LocaleProvider } from "../providers/LocaleProvider";
import { ProfilesPage } from "./ProfilesPage";
import type { TrainingProfile } from "../analyst/types";
const json = (data: unknown) => new Response(JSON.stringify(data), { headers: { "Content-Type": "application/json" } });
const view = () => render(<MemoryRouter><LocaleProvider><ProfilesPage/></LocaleProvider></MemoryRouter>);
beforeEach(() => localStorage.setItem("dashanbing-locale", "en"));

test("creates, edits confirmed goals and notes, reads retained history, and deletes a player profile", async () => {
  let profiles: TrainingProfile[] = [];
  vi.stubGlobal("fetch", vi.fn(async (input: string, init?: RequestInit) => {
    if (input.endsWith("/history")) return json([{ id: "h1", profile_id: "p1", task_id: null, occurred_at: "2026-09-01T12:00:00Z", mode: "quick", metrics: { shots: { attempts: 5, makes: 3, make_rate: .6 } }, media_available: false }]);
    if (init?.method === "POST") { profiles = [{ ...JSON.parse(String(init.body)), id: "p1", created_at: "2026-09-05", updated_at: "2026-09-05" }]; return json(profiles[0]); }
    if (init?.method === "PATCH") { profiles[0] = { ...profiles[0], ...JSON.parse(String(init.body)) }; return json(profiles[0]); }
    if (init?.method === "DELETE") { profiles = []; return new Response(null, { status: 204 }); }
    return json(profiles);
  }));
  const user = userEvent.setup(); view();
  await user.click(await screen.findByRole("button", { name: "New profile" }));
  await user.type(screen.getByLabelText("Name"), "Alex");
  await user.type(screen.getByLabelText("Training goals"), "Balance");
  await user.type(screen.getByLabelText("Confirmed notes"), "Left-handed");
  await user.click(screen.getByRole("button", { name: "Save" }));
  expect(await screen.findByRole("heading", { name: "Alex" })).toBeVisible();
  expect(screen.getByText("Left-handed")).toBeVisible();
  expect(await screen.findByText("Metrics retained")).toBeVisible();
  expect(screen.queryByRole("link", { name: "Open training session" })).not.toBeInTheDocument();
  await user.click(screen.getByRole("button", { name: "Edit profile" }));
  await user.clear(screen.getByLabelText("Training goals"));
  await user.type(screen.getByLabelText("Training goals"), "Footwork");
  await user.click(screen.getByRole("button", { name: "Save" }));
  expect(await screen.findByText("Footwork")).toBeVisible();
  await user.click(screen.getByRole("button", { name: "Delete profile" }));
  await user.click(within(screen.getByRole("dialog")).getByRole("button", { name: "Delete profile" }));
  await waitFor(() => expect(screen.queryByRole("heading", { name: "Alex" })).not.toBeInTheDocument());
  expect(screen.getByText("Create a player or team profile to track goals and progress")).toBeVisible();
});

test("profile errors preserve the editable draft and never announce success", async () => {
  vi.stubGlobal("fetch", vi.fn(async (_input, init?: RequestInit) => init?.method === "POST" ? new Response(JSON.stringify({ detail: "Try later" }), { status: 503 }) : json([])));
  const user = userEvent.setup(); view();
  await user.click(await screen.findByRole("button", { name: "New profile" }));
  await user.selectOptions(screen.getByLabelText("Profile type"), "team");
  await user.type(screen.getByLabelText("Name"), "Team A");
  await user.click(screen.getByRole("button", { name: "Save" }));
  expect(await screen.findByRole("alert")).toHaveTextContent("Unable to save");
  expect(screen.getByLabelText("Name")).toHaveValue("Team A");
  expect(screen.getByRole("button", { name: "Save" })).toBeEnabled();
});
