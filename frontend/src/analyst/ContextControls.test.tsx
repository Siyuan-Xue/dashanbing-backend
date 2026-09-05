import { useState } from "react";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, test, vi } from "vitest";
import { LocaleProvider } from "../providers/LocaleProvider";
import { ContextControls } from "./ContextControls";
import type { AnalystContext } from "./types";

const context = { task_id: "t1", facts: {}, subjects: [{ id: "s1", label: "Player 1", profile_id: "p1" }, { id: "s2", label: "Player 2", profile_id: "p2" }], team_profile_id: "team1", comparison_id: "h-team", comparisons: [{ id: "h-team", profile_id: "team1", task_id: "old-team", occurred_at: "2026-09-01", mode: "quick", metrics: {}, media_available: true }, { id: "h-player", profile_id: "p1", task_id: null, occurred_at: "2026-09-02", mode: "quick", metrics: {}, media_available: false }] } as unknown as AnalystContext;
const profiles = [{ id: "p1", kind: "player", name: "Alex" }, { id: "p2", kind: "player", name: "Blair" }, { id: "team1", kind: "team", name: "Team A" }];
function Harness({ initial = context }: { initial?: AnalystContext }) {
  const [value, setValue] = useState(initial); const [subject, setSubject] = useState("");
  return <><ContextControls source={{ kind: "task", id: "t1" }} subjects={value.subjects} context={value} subjectId={subject} onSubject={setSubject} onContext={setValue} onRetry={() => {}}/><output data-testid="global-comparison">{value.comparison_id || "none"}</output></>;
}

test("switching players filters unrelated history without invalidating the global report; retained personal metrics remain selectable", async () => {
  localStorage.setItem("dashanbing-locale", "en");
  vi.stubGlobal("fetch", vi.fn(async (url: string, init?: RequestInit) => url.endsWith("/context") ? Response.json({ ...context, ...JSON.parse(String(init?.body)) }) : Response.json(profiles)));
  const user = userEvent.setup(); render(<LocaleProvider><Harness/></LocaleProvider>);
  await user.selectOptions(screen.getByLabelText("Current player"), "s1");
  expect(screen.getByLabelText("Current player")).toHaveValue("s1");
  expect(screen.getByTestId("global-comparison")).toHaveTextContent("h-team");
  expect(vi.mocked(fetch).mock.calls.some(([, init]) => init?.method === "PUT")).toBe(false);
  const comparison = screen.getByLabelText("Compare with");
  expect(comparison).toHaveValue("scoped");
  expect(within(comparison).queryByRole("option", { name: /Team A/ })).not.toBeInTheDocument();
  const retained = within(comparison).getByRole("option", { name: /Alex.*Metrics retained/ });
  expect(retained).toHaveValue("h-player"); expect(retained).toBeEnabled();
  await user.selectOptions(comparison, "h-player");
  await waitFor(() => expect(screen.getByTestId("global-comparison")).toHaveTextContent("h-player"));
  expect(fetch).toHaveBeenCalledWith("/api/v1/tasks/t1/analyst/context", expect.objectContaining({ method: "PUT", body: JSON.stringify({ subjects: [{ id: "s1", profile_id: "p1" }, { id: "s2", profile_id: "p2" }], team_profile_id: "team1", comparison_id: "h-player" }) }));
});

test("a matching player comparison is selected, hidden for another player, and preserved when returning to all players", async () => {
  localStorage.setItem("dashanbing-locale", "en");
  vi.stubGlobal("fetch", vi.fn(async () => Response.json(profiles)));
  const user = userEvent.setup(); render(<LocaleProvider><Harness initial={{ ...context, comparison_id: "h-player" }}/></LocaleProvider>);
  await user.selectOptions(screen.getByLabelText("Current player"), "s1");
  expect(screen.getByLabelText("Compare with")).toHaveValue("h-player");
  await user.selectOptions(screen.getByLabelText("Current player"), "s2");
  expect(screen.getByLabelText("Compare with")).toHaveValue("scoped");
  expect(within(screen.getByLabelText("Compare with")).getAllByRole("option")).toHaveLength(2);
  await user.selectOptions(screen.getByLabelText("Current player"), "");
  expect(screen.getByLabelText("Compare with")).toHaveValue("h-player");
  expect(vi.mocked(fetch).mock.calls.some(([, init]) => init?.method === "PUT")).toBe(false);
});
