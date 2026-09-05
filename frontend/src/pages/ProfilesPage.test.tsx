import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, expect, test, vi } from "vitest";
import { LocaleProvider } from "../providers/LocaleProvider";
import { ProfileDetailPage } from "./ProfileDetailPage";
import { ProfilesPage } from "./ProfilesPage";
import type { TrainingProfile } from "../analyst/types";
const json = (data: unknown) => new Response(JSON.stringify(data), { headers: { "Content-Type": "application/json" } });
const view = () => render(<MemoryRouter initialEntries={["/workspace/profiles"]}><LocaleProvider><Routes><Route path="/workspace/profiles" element={<ProfilesPage/>}/><Route path="/workspace/profiles/:profileId" element={<ProfileDetailPage/>}/></Routes></LocaleProvider></MemoryRouter>);
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
  await user.click((await screen.findAllByRole("button", { name: "New profile" }))[0]);
  await user.type(screen.getByLabelText("Name"), "Alex");
  await user.type(screen.getByLabelText("Training goals"), "Balance");
  await user.type(screen.getByLabelText("Additional notes"), "Left-handed");
  await user.click(screen.getByRole("button", { name: "Save" }));
  await user.click(await screen.findByRole("link", { name: "Alex" }));
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
  expect(await screen.findByText("Create a player or team profile to track goals and progress")).toBeVisible();
});

test("profile errors preserve the editable draft and never announce success", async () => {
  vi.stubGlobal("fetch", vi.fn(async (_input, init?: RequestInit) => init?.method === "POST" ? new Response(JSON.stringify({ detail: "Try later" }), { status: 503 }) : json([])));
  const user = userEvent.setup(); view();
  await user.click((await screen.findAllByRole("button", { name: "New profile" }))[0]);
  await user.selectOptions(within(screen.getByRole("dialog")).getByLabelText("Profile type"), "team");
  await user.type(screen.getByLabelText("Name"), "Team A");
  await user.click(screen.getByRole("button", { name: "Save" }));
  expect(await screen.findByRole("alert")).toHaveTextContent("Unable to save");
  expect(screen.getByLabelText("Name")).toHaveValue("Team A");
  expect(screen.getByRole("button", { name: "Save" })).toBeEnabled();
});

test("shows a searchable table with type filtering and twenty profiles per page", async () => {
  const profiles = Array.from({ length: 21 }, (_, index) => ({ id: `p${index}`, name: `Player ${index}`, kind: index === 20 ? "team" : "player", goals: "Balance", notes: "", created_at: "2026-09-05", updated_at: "2026-09-05" }));
  vi.stubGlobal("fetch", vi.fn(async (input: string) => json(input.endsWith("/history") ? [] : profiles)));
  const user = userEvent.setup(); view();
  const table = await screen.findByRole("table");
  expect(within(table).getAllByRole("columnheader").map(cell => cell.textContent)).toEqual(["Name", "Profile type", "Training goals", "Updated", "Actions"]);
  expect(within(table).getAllByRole("row")).toHaveLength(21);
  await user.click(screen.getByRole("button", { name: "Next" }));
  expect(screen.getByRole("link", { name: "Player 20" })).toHaveAttribute("href", "/workspace/profiles/p20");
  await user.type(screen.getByRole("searchbox", { name: "Search profiles" }), "player 1");
  expect(screen.getByText("1 / 1")).toBeVisible();
  expect(within(table).getAllByRole("row")).toHaveLength(12);
  await user.selectOptions(screen.getByRole("combobox", { name: "Profile type" }), "team");
  expect(screen.getByRole("heading", { name: "No matching profiles" })).toBeVisible();
  await user.click(screen.getByRole("button", { name: "Clear filters" }));
  expect(screen.getByRole("searchbox")).toHaveValue("");
  expect(screen.getByRole("combobox")).toHaveValue("");
  expect(screen.getByText("1 / 2")).toBeVisible();
});

test("empty profiles offer creation and the modal traps focus and restores it on Escape", async () => {
  vi.stubGlobal("fetch", vi.fn(async () => json([])));
  const user = userEvent.setup(); view();
  const empty = (await screen.findByRole("heading", { name: "No training profiles yet" })).closest(".workspace-state")!;
  const trigger = within(empty as HTMLElement).getByRole("button", { name: "New profile" });
  await user.click(trigger);
  const dialog = screen.getByRole("dialog", { name: "New profile" });
  expect(within(dialog).getByLabelText("Name")).toHaveFocus();
  await user.type(screen.getByLabelText("Name"), "Alex");
  const save = within(dialog).getByRole("button", { name: "Save" });
  save.focus();
  await user.tab();
  expect(dialog).toContainElement(document.activeElement as HTMLElement);
  await user.keyboard("{Escape}");
  expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  expect(trigger).toHaveFocus();
});

test("editing a table row keeps the profile type and restores focus to its action", async () => {
  let profile = { id: "team1", kind: "team", name: "First team", goals: "Defense", notes: "", created_at: "2026-09-05", updated_at: "2026-09-05" };
  let update: unknown;
  vi.stubGlobal("fetch", vi.fn(async (input: string, init?: RequestInit) => {
    if (init?.method === "PATCH" && input.endsWith("/team1")) { update = JSON.parse(String(init.body)); profile = { ...profile, ...update as object }; return json(profile); }
    return json([profile]);
  }));
  const user = userEvent.setup(); view();
  const trigger = await screen.findByRole("button", { name: "Edit profile · First team" });
  await user.click(trigger);
  const dialog = within(screen.getByRole("dialog", { name: "Edit profile" }));
  expect(dialog.getByLabelText("Profile type")).toBeDisabled();
  expect(dialog.getByLabelText("Name")).toHaveFocus();
  await user.clear(dialog.getByLabelText("Name"));
  await user.type(dialog.getByLabelText("Name"), " Updated team ");
  await user.click(dialog.getByRole("button", { name: "Save" }));
  expect(await screen.findByRole("link", { name: "Updated team" })).toBeVisible();
  expect(update).toEqual({ name: "Updated team", goals: "Defense", notes: "" });
  expect(screen.getByRole("button", { name: "Edit profile · Updated team" })).toHaveFocus();
});

test("deletion failure preserves the row and deleting the last row on page two returns to page one", async () => {
  const profiles = Array.from({ length: 21 }, (_, i) => ({ id: `p${i}`, kind: "player", name: `Player ${i}`, goals: "", notes: "", created_at: "2026-09-05", updated_at: "2026-09-05" }));
  let deletes = 0;
  vi.stubGlobal("fetch", vi.fn(async (input: string, init?: RequestInit) => {
    if (init?.method === "DELETE" && input.endsWith("/p20")) return ++deletes === 1 ? new Response("{}", { status: 503 }) : new Response(null, { status: 204 });
    return json(profiles);
  }));
  const user = userEvent.setup(); view();
  await screen.findByRole("table");
  await user.click(screen.getByRole("button", { name: "Next" }));
  await user.click(screen.getByRole("button", { name: "Delete profile · Player 20" }));
  await user.click(within(screen.getByRole("dialog")).getByRole("button", { name: "Delete profile" }));
  expect(await screen.findByText("Unable to save, please retry")).toBeVisible();
  expect(screen.getByRole("link", { name: "Player 20" })).toBeVisible();
  await user.click(within(screen.getByRole("dialog")).getByRole("button", { name: "Delete profile" }));
  await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
  expect(screen.getByText("1 / 1")).toBeVisible();
  expect(screen.getByRole("link", { name: "Player 0" })).toBeVisible();
  expect(screen.getByRole("button", { name: "New profile" })).toHaveFocus();
});

test("profile list load errors offer a working retry", async () => {
  let reads = 0;
  vi.stubGlobal("fetch", vi.fn(async () => ++reads === 1 ? new Response("{}", { status: 503 }) : json([])));
  const user = userEvent.setup(); view();
  expect(await screen.findByRole("alert")).toHaveTextContent("Unable to load profiles");
  await user.click(screen.getByRole("button", { name: "Retry" }));
  expect(await screen.findByRole("heading", { name: "No training profiles yet" })).toBeVisible();
});

test("waits for the initial list before allowing creation so a late list cannot replace a saved profile", async () => {
  let resolveList!: (response: Response) => void;
  vi.stubGlobal("fetch", vi.fn(() => new Promise<Response>(resolve => { resolveList = resolve; })));
  view();
  const create = screen.getByRole("button", { name: "New profile" });
  expect(create).toBeDisabled();
  resolveList(json([]));
  await waitFor(() => expect(create).toBeEnabled());
});
