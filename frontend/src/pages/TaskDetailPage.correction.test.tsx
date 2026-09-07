import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { expect, test, vi } from "vitest";
import { LocaleProvider } from "../providers/LocaleProvider";
import { draftTask } from "../test/taskSyncFixture";
import { TaskDetailPage } from "./TaskDetailPage";

vi.mock("../providers/AuthProvider", () => ({ useAuth: () => ({ user: { id: 2 } }) }));
vi.mock("../components/ResultWorkspace", () => ({ ResultWorkspace: () => null }));

test("a registration failure offers correction without changing the task until confirmed", async () => {
  const fetch = vi.fn(async () => Response.json(draftTask({ status: "failed", error_code: "registration_count_mismatch", error_message: "Registration count mismatch" })));
  vi.stubGlobal("fetch", fetch);
  render(<MemoryRouter><LocaleProvider><TaskDetailPage taskId="draft-1"/></LocaleProvider></MemoryRouter>);
  expect(await screen.findByRole("link", { name: "修改输入" })).toHaveAttribute("href", "/workspace/new?draft=draft-1");
  expect(fetch.mock.calls).toHaveLength(1);
});

test("running tasks do not offer an input mutation", async () => {
  vi.stubGlobal("fetch", vi.fn(async () => Response.json(draftTask({ status: "running" }))));
  render(<MemoryRouter><LocaleProvider><TaskDetailPage taskId="draft-1"/></LocaleProvider></MemoryRouter>);
  await screen.findByRole("heading", { name: "训练草稿" });
  expect(screen.queryByRole("link", { name: "修改输入" })).not.toBeInTheDocument();
});
