import { expect, test, vi } from "vitest";
import { workspaceApi } from "./api";
import { draftTask } from "../test/taskSyncFixture";

test("create sends the contract's sequential default when registration is omitted", async () => {
  let sent: unknown;
  vi.stubGlobal("fetch", async (_url: RequestInfo | URL, init?: RequestInit) => {
    sent = JSON.parse(String(init?.body));
    return Response.json(draftTask());
  });
  await workspaceApi.createTask("Practice", "quick", "en");
  expect(sent).toEqual({ title: "Practice", mode: "quick", analyst_locale: "en", enrollment_mode: "sequential" });
});

test("create preserves an explicitly selected registration mode and person count", async () => {
  let sent: unknown;
  vi.stubGlobal("fetch", async (_url: RequestInfo | URL, init?: RequestInit) => {
    sent = JSON.parse(String(init?.body));
    return Response.json(draftTask({ enrollment_mode: "lineup", expected_persons: 3 }));
  });
  await workspaceApi.createTask("Practice", "full", "zh", { enrollment_mode: "lineup", expected_persons: 3 });
  expect(sent).toEqual({ title: "Practice", mode: "full", analyst_locale: "zh", enrollment_mode: "lineup", expected_persons: 3 });
});
