import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, useLocation } from "react-router-dom";
import { beforeEach, expect, test, vi } from "vitest";
import App from "./App";
import type { Task, TaskSlot } from "./workspace/types";

const slots: TaskSlot[] = ["enrollment_video", "cam_01", "cam_02", "cam_03", "cam_04"];
const input = (slot: TaskSlot, name = `${slot}.mp4`) => ({ slot, original_filename: name, byte_size: 100, validation_state: "valid", created_at: "2026-09-05T01:00:00Z", updated_at: "2026-09-05T01:00:00Z" });
const draft = (): Task => ({ id: "draft-1", title: "已有训练", mode: "quick", source_type: "upload", preset_id: null, status: "draft", progress: 0, stage_message: "Draft", error_code: null, error_message: null, submitted_at: null, created_via: "tasks_api", retry_count: 0, created_at: "2026-09-05T01:00:00Z", updated_at: "2026-09-05T01:00:00Z", started_at: null, completed_at: null, inputs: [] });

function Location() { const location = useLocation(); return <output data-testid="location">{location.pathname}{location.search}</output>; }
function open(path: string) { return render(<MemoryRouter initialEntries={[path]}><App/><Location/></MemoryRouter>); }

function installServer(initial = draft()) {
  let task = initial;
  let failSave = false;
  let creates = 0;
  let holdPatch = false;
  let holdUpload = false;
  let lastPatchTitle = "";
  const pendingPatches: Array<() => void> = [];
  const pendingUploads: Array<() => void> = [];
  vi.stubGlobal("fetch", vi.fn(async (path: RequestInfo | URL, init?: RequestInit) => {
    const url = new URL(String(path), "http://localhost");
    if (url.pathname === "/api/v1/users/me") return Response.json({ id: 7, username: "coach", email: "coach@example.com", is_active: true });
    if (url.pathname === "/api/v1/presets") return Response.json([]);
    if (url.pathname === "/api/v1/tasks") {
      if (init?.method === "POST") { creates++; task = { ...task, ...JSON.parse(init.body as string) }; return Response.json(task, { status: 201 }); }
      return Response.json({ items: [task], total: 1, page: 1, page_size: 20 });
    }
    if (url.pathname === `/api/v1/tasks/${task.id}`) {
      if (init?.method === "PATCH") {
        if (failSave) return Response.json({ detail: "保存失败" }, { status: 500 });
        task = { ...task, ...JSON.parse(init.body as string) };
        lastPatchTitle = task.title;
        if (holdPatch) {
          const snapshot = structuredClone(task);
          return new Promise<Response>(resolve => pendingPatches.push(() => resolve(Response.json(snapshot))));
        }
      }
      return Response.json(task);
    }
    if (url.pathname.endsWith("/submit")) { task = { ...task, status: "queued", stage_message: "Queued" }; return Response.json(task); }
    return Response.json({ detail: "Not found" }, { status: 404 });
  }));
  vi.stubGlobal("XMLHttpRequest", class {
    url = ""; status = 0; responseText = "";
    upload = { addEventListener() {} };
    listeners = new Map<string, () => void>();
    open(_method: string, url: string) { this.url = url; }
    addEventListener(name: string, listener: () => void) { this.listeners.set(name, listener); }
    send(body: FormData) {
      const slot = this.url.split("/").at(-1) as TaskSlot;
      const file = body.get("file") as File;
      const finish = () => {
        task = { ...task, inputs: [...task.inputs.filter(item => item.slot !== slot), input(slot, file.name)] };
        this.status = 200; this.responseText = JSON.stringify(task); this.listeners.get("load")?.();
      };
      if (holdUpload) pendingUploads.push(finish); else queueMicrotask(finish);
    }
  });
  return { get task() { return task; }, get creates() { return creates; }, get lastPatchTitle() { return lastPatchTitle; },
    pendingPatches, pendingUploads, holdPatch: (value = true) => { holdPatch = value; }, holdUpload: () => { holdUpload = true; },
    failSave: (value: boolean) => { failSave = value; } };
}

beforeEach(() => localStorage.clear());

test("uploads before naming, keeps fields editable and restores saved draft after reopening", async () => {
  const server = installServer();
  const user = userEvent.setup();
  const page = open("/workspace/new");
  await user.upload(await screen.findByLabelText("注册视频"), new File(["video"], "players.mp4", { type: "video/mp4" }));
  expect(await screen.findByText("players.mp4")).toBeVisible();
  expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  expect(screen.getByTestId("location")).toHaveTextContent("/workspace/new?draft=draft-1");
  const title = screen.getByLabelText("任务标题");
  expect(title).toBeEnabled();
  await user.clear(title);
  await user.type(title, "周末训练");
  await user.click(screen.getByRole("radio", { name: /完整/ }));
  await waitFor(() => expect(server.task).toMatchObject({ title: "周末训练", mode: "full" }));
  expect(screen.getByText("点击替换")).toBeVisible();
  page.unmount();
  open("/workspace/new?draft=draft-1");
  expect(await screen.findByDisplayValue("周末训练")).toBeEnabled();
  expect(screen.getByRole("radio", { name: /完整/ })).toBeChecked();
  expect(screen.getByText("players.mp4")).toBeVisible();
  expect(screen.getByText(/已验证视频 1 \/ 5/)).toBeVisible();
  expect(server.creates).toBe(1);
});

test("opens a draft from task history as an upload form and submits its existing five files", async () => {
  const server = installServer({ ...draft(), inputs: slots.map(slot => input(slot)) });
  const user = userEvent.setup();
  open("/workspace/tasks");
  const table = await screen.findByRole("table");
  await user.click(within(table).getByRole("link", { name: /已有训练/ }));
  expect(await screen.findByLabelText("注册视频")).toBeVisible();
  expect(screen.getAllByText("点击替换")).toHaveLength(5);
  const submit = screen.getByRole("button", { name: "提交分析" });
  expect(submit).toBeEnabled();
  await user.click(submit);
  await waitFor(() => expect(server.task.status).toBe("queued"));
  await waitFor(() => expect(screen.getByTestId("location")).toHaveTextContent("/workspace/tasks/draft-1"));
  expect(server.creates).toBe(0);
});

test("does not submit a draft with unsaved metadata when saving fails", async () => {
  const server = installServer({ ...draft(), inputs: slots.map(slot => input(slot)) });
  server.failSave(true);
  const user = userEvent.setup();
  open("/workspace/new?draft=draft-1");
  const title = await screen.findByDisplayValue("已有训练");
  fireEvent.change(title, { target: { value: "新的名称" } });
  await user.click(screen.getByRole("button", { name: "提交分析" }));
  expect(await screen.findByRole("alert")).toHaveTextContent("保存失败");
  expect(server.task.status).toBe("draft");
  server.failSave(false);
  await user.click(screen.getByRole("button", { name: "提交分析" }));
  await waitFor(() => expect(server.task).toMatchObject({ title: "新的名称", status: "queued" }));
});

test("enforces the title length at submission and accepts 120 Unicode characters", async () => {
  const server = installServer({ ...draft(), inputs: slots.map(slot => input(slot)) });
  const user = userEvent.setup();
  open("/workspace/new?draft=draft-1");
  const title = await screen.findByDisplayValue("已有训练");
  fireEvent.change(title, { target: { value: "🏀".repeat(121) } });
  await user.click(screen.getByRole("button", { name: "提交分析" }));
  expect(await screen.findByRole("alert")).toHaveTextContent("任务标题不能超过 120 个字符");
  expect(server.task.status).toBe("draft");
  fireEvent.change(title, { target: { value: "🏀".repeat(120) } });
  await user.click(screen.getByRole("button", { name: "提交分析" }));
  await waitFor(() => expect(server.task).toMatchObject({ title: "🏀".repeat(120), status: "queued" }));
});

test("late metadata responses cannot roll back restored upload progress", async () => {
  const server = installServer({ ...draft(), status: "uploading", inputs: [input("enrollment_video")] });
  server.holdPatch();
  const user = userEvent.setup();
  open("/workspace/new?draft=draft-1");
  const title = await screen.findByDisplayValue("已有训练");
  fireEvent.change(title, { target: { value: "新训练" } });
  await user.tab();
  await waitFor(() => expect(server.pendingPatches).toHaveLength(1));
  server.task.status = "draft";
  server.task.inputs = [input("enrollment_video"), input("cam_01")];
  await waitFor(() => expect(screen.getByText(/已验证视频 2 \/ 5/)).toBeVisible(), { timeout: 3500 });
  server.holdPatch(false);
  await act(async () => server.pendingPatches.shift()!());
  await waitFor(() => expect(screen.getByLabelText("机位 2")).toBeEnabled());
  expect(screen.getByText(/已验证视频 2 \/ 5/)).toBeVisible();
});

test("late submission cannot navigate away from a new draft", async () => {
  const server = installServer({ ...draft(), inputs: slots.map(slot => input(slot)) });
  server.holdPatch();
  const user = userEvent.setup();
  open("/workspace/new?draft=draft-1");
  fireEvent.change(await screen.findByDisplayValue("已有训练"), { target: { value: "已提交训练" } });
  await user.click(screen.getByRole("button", { name: "提交分析" }));
  await waitFor(() => expect(server.pendingPatches).toHaveLength(1));
  await user.click(screen.getByRole("link", { name: "创建任务" }));
  fireEvent.change(screen.getByLabelText("任务标题"), { target: { value: "下一次训练" } });
  server.holdPatch(false);
  await act(async () => server.pendingPatches.shift()!());
  await waitFor(() => expect(server.task.status).toBe("queued"));
  expect(screen.getByTestId("location")).toHaveTextContent(/^\/workspace\/new$/);
  expect(screen.getByLabelText("任务标题")).toHaveValue("下一次训练");
});

test("queued edits retain the last name after leaving during an upload", async () => {
  const server = installServer({ ...draft(), title: "训练 A", inputs: [input("enrollment_video")] });
  server.holdUpload();
  const user = userEvent.setup();
  open("/workspace/new?draft=draft-1");
  const title = await screen.findByDisplayValue("训练 A");
  await user.upload(screen.getByLabelText("机位 1"), new File(["video"], "cam.mp4", { type: "video/mp4" }));
  fireEvent.change(title, { target: { value: "训练 B" } });
  fireEvent.blur(title);
  fireEvent.change(title, { target: { value: "训练 A" } });
  fireEvent.blur(title);
  await user.click(screen.getByRole("link", { name: "创建任务" }));
  await act(async () => server.pendingUploads.shift()!());
  await waitFor(() => expect(server.lastPatchTitle).toBe("训练 A"));
  expect(server.task.title).toBe("训练 A");
  expect(screen.getByLabelText("任务标题")).toHaveValue("");
});
