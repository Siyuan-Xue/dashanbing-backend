import { useState } from "react";
import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, expect, test, vi } from "vitest";
import { LocaleProvider } from "../providers/LocaleProvider";
import { ProfileBindingsDialog } from "./ProfileBindingsDialog";
import type { AnalystContext, TrainingProfile } from "./types";

const context: AnalystContext = {
  task_id: "session-1",
  facts: {
    schema_version: 1,
    metrics: { action_counts: {}, shots: {}, registered_participant_count: 3, event_count: 0 },
    subjects: [{ id: "s1", label: "Player 1" }, { id: "s2", label: "Player 2" }, { id: "s3", label: "Player 3" }],
    evidence: [], warnings: [], pose_available: false,
  },
  subjects: [{ id: "s1", label: "Player 1", profile_id: "p1" }, { id: "s2", label: "Player 2", profile_id: "p2" }, { id: "s3", label: "Player 3" }],
  team_profile_id: "team1", comparison_id: "h-player",
  comparisons: [
    { id: "h-player", profile_id: "p1", task_id: "old-player", occurred_at: "2026-09-01", mode: "quick", metrics: {}, media_available: true },
    { id: "h-team", profile_id: "team1", task_id: null, occurred_at: "2026-09-02", mode: "quick", metrics: {}, media_available: false },
  ],
};
const profiles: TrainingProfile[] = [
  { id: "p1", kind: "player", name: "Alex", goals: "Footwork", notes: "", created_at: "2026-09-01", updated_at: "2026-09-01" },
  { id: "p2", kind: "player", name: "Blair", goals: "", notes: "", created_at: "2026-09-01", updated_at: "2026-09-01" },
  { id: "p3", kind: "player", name: "Casey", goals: "", notes: "", created_at: "2026-09-01", updated_at: "2026-09-01" },
  { id: "team1", kind: "team", name: "Team A", goals: "", notes: "", created_at: "2026-09-01", updated_at: "2026-09-01" },
  { id: "team2", kind: "team", name: "Team B", goals: "", notes: "", created_at: "2026-09-01", updated_at: "2026-09-01" },
];
const firstSession: AnalystContext = {
  ...context,
  subjects: [{ id: "s1", label: "Player 1" }, { id: "s2", label: "Player 2", profile_id: null }, { id: "s3", label: "Player 3" }],
  team_profile_id: null, comparison_id: null,
};
const savedResponse: AnalystContext = {
  ...firstSession,
  subjects: [{ id: "s1", label: "Player 1", profile_id: "p1" }, { id: "s2", label: "Player 2", profile_id: "p2" }, { id: "s3", label: "Player 3", profile_id: null }],
  team_profile_id: "team2",
  facts: { ...context.facts, warnings: ["Response from server"] },
};

function Harness({ initial }: { initial: AnalystContext }) {
  const [saved, setSaved] = useState(initial);
  const [saveCount, setSaveCount] = useState(0);
  const [open, setOpen] = useState(false);
  return <>
    <button onClick={() => setOpen(true)}>Bind profiles</button>
    <output data-testid="saved-context">{JSON.stringify(saved)}</output>
    <output data-testid="save-count">{saveCount}</output>
    {open && <ProfileBindingsDialog source={{ kind: "task", id: "session-1" }} context={saved} onSaved={value => { setSaved(value); setSaveCount(count => count + 1); }} onClose={() => setOpen(false)}/>}
  </>;
}

function mockApi({ load = async () => Response.json(profiles), save = async () => Response.json(savedResponse) }: {
  load?: () => Promise<Response>; save?: () => Promise<Response>;
} = {}) {
  vi.stubGlobal("fetch", vi.fn(async (url: RequestInfo | URL, init?: RequestInit) => {
    if (url === "/api/v1/training-profiles" && (!init?.method || init.method === "GET")) return load();
    if (url === "/api/v1/tasks/session-1/analyst/context" && init?.method === "PUT") return save();
    throw new Error(`Unexpected request: ${init?.method || "GET"} ${url}`);
  }));
}

function writes() {
  return vi.mocked(fetch).mock.calls.filter(([, init]) => init?.method && init.method !== "GET");
}

async function openDialog(initial = context, locale = "en") {
  localStorage.setItem("dashanbing-locale", locale);
  const user = userEvent.setup();
  render(<LocaleProvider><Harness initial={initial}/></LocaleProvider>);
  await user.click(screen.getByRole("button", { name: "Bind profiles" }));
  return user;
}

async function loaded() {
  await waitFor(() => expect(screen.getByLabelText("Player 1")).toBeEnabled());
}

afterEach(() => vi.unstubAllGlobals());

test("loads every anonymous player and the team with only the matching kind of profile", async () => {
  mockApi();
  await openDialog();
  await loaded();
  const dialog = screen.getByRole("dialog", { name: "Bind profiles" });
  expect(within(dialog).getAllByRole("combobox")).toHaveLength(4);
  for (const label of ["Player 1", "Player 2", "Player 3"]) {
    const select = screen.getByLabelText(label);
    expect(within(select).getAllByRole("option").map(option => option.textContent)).toEqual(["Not linked", "Alex", "Blair", "Casey"]);
  }
  expect(within(screen.getByLabelText("Team")).getAllByRole("option").map(option => option.textContent)).toEqual(["Not linked", "Team A", "Team B"]);
  expect(dialog).toHaveAccessibleDescription("Confirm to save this session to the selected profiles");
  expect(writes()).toHaveLength(0);
});

test("keeps edits local until Confirm and sends one complete atomic payload with explicit null on first binding", async () => {
  mockApi();
  const user = await openDialog(firstSession);
  await loaded();
  await user.selectOptions(screen.getByLabelText("Player 1"), "p1");
  await user.selectOptions(screen.getByLabelText("Player 2"), "p2");
  await user.selectOptions(screen.getByLabelText("Team"), "team2");
  expect(writes()).toHaveLength(0);
  expect(screen.getByTestId("saved-context")).toHaveTextContent(JSON.stringify(firstSession));
  await user.click(screen.getByRole("button", { name: "Confirm" }));
  await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
  expect(writes()).toHaveLength(1);
  expect(JSON.parse(String(writes()[0][1]?.body))).toEqual({
    subjects: [{ id: "s1", profile_id: "p1" }, { id: "s2", profile_id: "p2" }, { id: "s3", profile_id: null }],
    team_profile_id: "team2", comparison_id: null,
  });
  expect(writes()[0][1]).toMatchObject({ credentials: "include", headers: { "Content-Type": "application/json" } });
  expect(JSON.parse(screen.getByTestId("saved-context").textContent!)).toEqual(savedResponse);
});

test.each(["Cancel", "Escape", "backdrop"])("%s discards edits without writing and reopening restores saved bindings", async (dismiss) => {
  mockApi();
  const user = await openDialog();
  await loaded();
  await user.selectOptions(screen.getByLabelText("Player 1"), "p3");
  await user.selectOptions(screen.getByLabelText("Team"), "");
  if (dismiss === "Cancel") await user.click(screen.getByRole("button", { name: "Cancel" }));
  else if (dismiss === "Escape") await user.keyboard("{Escape}");
  else fireEvent.mouseDown(screen.getByRole("dialog").parentElement!);
  expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  expect(writes()).toHaveLength(0);
  await user.click(screen.getByRole("button", { name: "Bind profiles" }));
  await loaded();
  expect(screen.getByLabelText("Player 1")).toHaveValue("p1");
  expect(screen.getByLabelText("Team")).toHaveValue("team1");
});

test("prevents duplicate player bindings and releases a profile after unlinking it", async () => {
  mockApi();
  const user = await openDialog();
  await loaded();
  const third = screen.getByLabelText("Player 3");
  expect(within(third).getByRole("option", { name: "Alex" })).toBeDisabled();
  await user.selectOptions(third, "p1");
  expect(third).toHaveValue("");
  await user.selectOptions(screen.getByLabelText("Player 1"), "");
  expect(within(third).getByRole("option", { name: "Alex" })).toBeEnabled();
  await user.selectOptions(third, "p1");
  expect(within(screen.getByLabelText("Player 1")).getByRole("option", { name: "Alex" })).toBeDisabled();
  await user.click(screen.getByRole("button", { name: "Confirm" }));
  expect(JSON.parse(String(writes()[0][1]?.body))).toEqual({
    subjects: [{ id: "s1", profile_id: null }, { id: "s2", profile_id: "p2" }, { id: "s3", profile_id: "p1" }],
    team_profile_id: "team1", comparison_id: null,
  });
});

test("existing duplicate bindings cannot be confirmed until the user resolves them", async () => {
  mockApi();
  const user = await openDialog({ ...context, subjects: [{ id: "s1", label: "Player 1", profile_id: "p1" }, { id: "s2", label: "Player 2", profile_id: "p1" }] });
  await loaded();
  expect(screen.getByRole("alert")).toHaveTextContent(/one player|already linked/i);
  await user.click(screen.getByRole("button", { name: "Confirm" }));
  expect(writes()).toHaveLength(0);
  await user.selectOptions(screen.getByLabelText("Player 2"), "p2");
  await user.click(screen.getByRole("button", { name: "Confirm" }));
  expect(writes()).toHaveLength(1);
});

test.each([
  { comparison: "h-player", field: "Team", selection: "", expected: null },
  { comparison: "h-player", field: "Player 1", selection: "", expected: null },
  { comparison: "h-team", field: "Player 1", selection: "p3", expected: null },
  { comparison: "h-team", field: "Team", selection: "team2", expected: null },
  { comparison: "missing-history", field: "Team", selection: "team2", expected: null },
])("clears legacy comparison $comparison while saving changed $field bindings", async ({ comparison, field, selection, expected }) => {
  mockApi();
  const user = await openDialog({ ...context, comparison_id: comparison });
  await loaded();
  await user.selectOptions(screen.getByLabelText(field), selection);
  await user.click(screen.getByRole("button", { name: "Confirm" }));
  expect(writes()).toHaveLength(1);
  expect(JSON.parse(String(writes()[0][1]?.body)).comparison_id).toBe(expected);
});

test("first binding clears even a stale comparison that happens to match the newly selected profile", async () => {
  mockApi();
  const user = await openDialog({ ...firstSession, comparison_id: "h-player" });
  await loaded();
  await user.selectOptions(screen.getByLabelText("Player 1"), "p1");
  await user.click(screen.getByRole("button", { name: "Confirm" }));
  expect(JSON.parse(String(writes()[0][1]?.body)).comparison_id).toBeNull();
});

test("a failed save retains the draft and saved context, and Confirm retries the same atomic payload", async () => {
  let attempts = 0;
  mockApi({ save: async () => ++attempts === 1 ? Response.json({ detail: "Service unavailable" }, { status: 503 }) : Response.json(savedResponse) });
  const user = await openDialog();
  await loaded();
  await user.selectOptions(screen.getByLabelText("Player 1"), "p3");
  await user.selectOptions(screen.getByLabelText("Team"), "");
  await user.click(screen.getByRole("button", { name: "Confirm" }));
  expect(await screen.findByRole("alert")).toHaveTextContent(/save|try again/i);
  expect(screen.getByLabelText("Player 1")).toHaveValue("p3");
  expect(screen.getByLabelText("Team")).toHaveValue("");
  expect(screen.getByTestId("saved-context")).toHaveTextContent(JSON.stringify(context));
  const payload = { subjects: [{ id: "s1", profile_id: "p3" }, { id: "s2", profile_id: "p2" }, { id: "s3", profile_id: null }], team_profile_id: null, comparison_id: null };
  expect(JSON.parse(String(writes()[0][1]?.body))).toEqual(payload);
  await user.click(screen.getByRole("button", { name: "Confirm" }));
  await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
  expect(writes()).toHaveLength(2);
  expect(JSON.parse(String(writes()[1][1]?.body))).toEqual(payload);
});

test("repeated Confirm clicks issue one PUT and keep the dialog stable during the request", async () => {
  let finish!: (response: Response) => void;
  const response = new Promise<Response>(resolve => { finish = resolve; });
  mockApi({ save: () => response });
  const user = await openDialog();
  await loaded();
  await user.selectOptions(screen.getByLabelText("Player 1"), "p3");
  const confirm = screen.getByRole("button", { name: "Confirm" });
  act(() => { confirm.click(); confirm.click(); });
  await user.dblClick(confirm);
  expect(writes()).toHaveLength(1);
  expect(confirm).toBeDisabled();
  expect(screen.getByLabelText("Player 1")).toBeDisabled();
  expect(screen.getByRole("button", { name: "Cancel" })).toBeDisabled();
  await user.keyboard("{Enter}{Escape}{Tab}");
  fireEvent.mouseDown(screen.getByRole("dialog").parentElement!);
  expect(screen.getByRole("dialog")).toBeInTheDocument();
  expect(screen.getByRole("dialog")).toHaveFocus();
  expect(writes()).toHaveLength(1);
  await act(async () => finish(Response.json(savedResponse)));
  await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
});

test("loading failures offer Retry and never allow a save before profiles are loaded", async () => {
  let attempts = 0;
  mockApi({ load: async () => ++attempts === 1 ? Response.json({ detail: "Unavailable" }, { status: 503 }) : Response.json(profiles) });
  const user = await openDialog();
  expect(await screen.findByRole("alert")).toHaveTextContent(/load/i);
  expect(screen.getByLabelText("Player 1")).toBeDisabled();
  expect(screen.getByRole("button", { name: "Confirm" })).toBeDisabled();
  await user.click(screen.getByRole("button", { name: "Retry" }));
  await loaded();
  expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  expect(screen.getByLabelText("Player 1")).toHaveValue("p1");
  expect(attempts).toBe(2);
  expect(writes()).toHaveLength(0);
});

test("empty profiles offer the profiles page and still allow existing bindings to be explicitly removed", async () => {
  mockApi({ load: async () => Response.json([]) });
  const user = await openDialog();
  await loaded();
  expect(screen.getByRole("link", { name: /profiles/i })).toHaveAttribute("href", "/workspace/profiles");
  for (const label of ["Player 1", "Player 2", "Team"]) await user.selectOptions(screen.getByLabelText(label), "");
  await user.click(screen.getByRole("button", { name: "Confirm" }));
  expect(JSON.parse(String(writes()[0][1]?.body))).toEqual({
    subjects: [{ id: "s1", profile_id: null }, { id: "s2", profile_id: null }, { id: "s3", profile_id: null }],
    team_profile_id: null, comparison_id: null,
  });
});

test("traps Tab in both directions, supports keyboard confirmation, and restores body scrolling and trigger focus", async () => {
  mockApi();
  const previousOverflow = document.body.style.overflow;
  document.body.style.overflow = "clip";
  try {
    const user = await openDialog();
    await loaded();
    const dialog = screen.getByRole("dialog");
    expect(dialog).toHaveAttribute("aria-modal", "true");
    expect(screen.getByRole("button", { name: "Cancel" })).toHaveFocus();
    expect(document.body.style.overflow).toBe("hidden");
    await user.selectOptions(screen.getByLabelText("Player 1"), "p3");
    await user.click(screen.getByRole("heading", { name: "Bind profiles" }));
    expect(dialog).toBeInTheDocument();
    screen.getByLabelText("Player 1").focus();
    await user.tab({ shift: true });
    expect(screen.getByRole("button", { name: "Confirm" })).toHaveFocus();
    await user.tab();
    expect(screen.getByLabelText("Player 1")).toHaveFocus();
    screen.getByRole("button", { name: "Bind profiles" }).focus();
    await user.tab();
    expect(screen.getByLabelText("Player 1")).toHaveFocus();
    screen.getByRole("button", { name: "Confirm" }).focus();
    await user.keyboard("{Enter}");
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    expect(writes()).toHaveLength(1);
    expect(document.body.style.overflow).toBe("clip");
    expect(screen.getByRole("button", { name: "Bind profiles" })).toHaveFocus();
  } finally { document.body.style.overflow = previousOverflow; }
});

test("uses local Chinese copy and closes through the localized cancel action", async () => {
  mockApi();
  const user = await openDialog(context, "zh");
  await loaded();
  expect(screen.getByRole("dialog", { name: "绑定档案" })).toHaveAccessibleDescription("确认后将本场训练记录存入对应档案");
  expect(screen.getByLabelText("球队")).toHaveValue("team1");
  expect(screen.getByRole("button", { name: "确认" })).toBeEnabled();
  await user.click(screen.getByRole("button", { name: "取消" }));
  expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  expect(writes()).toHaveLength(0);
});

test.each(["unchanged", "reverted"])("Confirm closes %s bindings without a PUT or onSaved notification", async (mode) => {
  mockApi();
  const user = await openDialog();
  await loaded();
  if (mode === "reverted") {
    await user.selectOptions(screen.getByLabelText("Player 1"), "p3");
    await user.selectOptions(screen.getByLabelText("Team"), "");
    await user.selectOptions(screen.getByLabelText("Player 1"), "p1");
    await user.selectOptions(screen.getByLabelText("Team"), "team1");
  }
  await user.click(screen.getByRole("button", { name: "Confirm" }));
  expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  expect(writes()).toHaveLength(0);
  expect(screen.getByTestId("save-count")).toHaveTextContent("0");
  expect(screen.getByTestId("saved-context")).toHaveTextContent(JSON.stringify(context));
});

test.each([
  { locale: "en", labels: ["Player 1", "Player 12", "Captain 球员 3"] },
  { locale: "zh", labels: ["球员 1", "球员 12", "Captain 球员 3"] },
])("localizes only anonymous backend player labels in $locale", async ({ locale, labels }) => {
  mockApi();
  await openDialog({ ...context, subjects: [
    { id: "s1", label: "球员 1", profile_id: "p1" },
    { id: "s2", label: "球员 12", profile_id: "p2" },
    { id: "s3", label: "Captain 球员 3", profile_id: null },
  ] }, locale);
  await waitFor(() => expect(screen.getByLabelText(labels[0])).toBeEnabled());
  expect(screen.getByLabelText(labels[0])).toHaveValue("p1");
  expect(screen.getByLabelText(labels[1])).toHaveValue("p2");
  expect(screen.getByLabelText(labels[2])).toHaveValue("");
  expect(writes()).toHaveLength(0);
});
