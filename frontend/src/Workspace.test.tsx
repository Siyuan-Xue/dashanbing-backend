import { act } from "react";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, useLocation, useNavigate } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";

import App from "./App";
import { ResultWorkspace } from "./components/ResultWorkspace";
import { LocaleProvider } from "./providers/LocaleProvider";
import { taskStageMessageLabel } from "./workspace/labels";
import type { Task } from "./workspace/types";
import "./styles.css";

const currentUser = { id: 7, username: "coach", email: "coach@example.com", is_active: true };
const slots = ["enrollment_video", "cam_01", "cam_02", "cam_03", "cam_04"] as const;

const task = (overrides: Record<string, unknown> = {}) => ({
  id: "task-1",
  title: "周三投篮训练",
  mode: "quick",
  source_type: "upload",
  preset_id: null,
  status: "draft",
  progress: 0,
  stage_message: "Draft",
  error_code: null,
  error_message: null,
  submitted_at: null,
  created_via: "tasks_api",
  retry_count: 0,
  created_at: "2026-09-05T01:00:00Z",
  updated_at: "2026-09-05T01:00:00Z",
  started_at: null,
  completed_at: null,
  inputs: [],
  ...overrides,
});

const presets = [
  { id: "quick-demo", title: "快速演示", description: "4 次跳投", expected_minutes: 9.4 },
  { id: "mixed-actions", title: "混合动作", description: "三威胁与跳投", expected_minutes: 26.7 },
  { id: "verified-outcome", title: "命中验证", description: "带投篮结果真值的罚篮样例", expected_minutes: 30.9 },
  { id: "layup-demo", title: "上篮演示", description: "6 次上篮", expected_minutes: 14.3 },
];

const productResult = {
  registered_participant_count: 2,
  action_counts: { triple_threat: 1, free_throw: 0, jump_shot: 4, layup: 1 },
  unsupported_event_count: 0,
  shots: { attempts: 5, makes: 3, misses: 1, undetermined: 1, make_rate: 0.6, unlinked_outcomes: 0 },
  events: [{ event_index: 1, action_type: "jump_shot", start_ms: 1000, end_ms: 2200, time_ms: 1800, result: "make" }],
  media: {
    phases: "/api/v1/tasks/task-1/media/phases",
    cam_01: "/api/v1/tasks/task-1/media/cam_01",
    cam_02: "/api/v1/tasks/task-1/media/cam_02",
    cam_03: "/api/v1/tasks/task-1/media/cam_03",
    cam_04: "/api/v1/tasks/task-1/media/cam_04",
  },
  warnings: [],
  disclaimer: "AI 识别结果，仅供训练复盘。",
};

function LocationProbe() {
  const location = useLocation();
  const navigate = useNavigate();
  return <><output data-testid="workspace-location">{location.pathname}{location.search}</output><button type="button" onClick={() => navigate(-1)}>History back</button></>;
}

function renderAt(path: string) {
  return render(<MemoryRouter initialEntries={[path]}><App/><LocationProbe/></MemoryRouter>);
}

function renderHistory(entries: string[], initialIndex: number) {
  return render(<MemoryRouter initialEntries={entries} initialIndex={initialIndex}><App/><LocationProbe/></MemoryRouter>);
}

function json(value: unknown, init?: ResponseInit) {
  return Response.json(value, init);
}

function requestPath(input: RequestInfo | URL) {
  return new URL(String(input), "http://localhost");
}

async function flushPromises() {
  await act(async () => {
    for (let index = 0; index < 8; index += 1) await Promise.resolve();
  });
}

function installBaseFetch(handler?: (url: URL, init?: RequestInit) => Response | Promise<Response> | undefined) {
  const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = requestPath(input);
    if (url.pathname === "/api/v1/users/me") return json(currentUser);
    const handled = handler?.(url, init);
    if (handled) return handled;
    if (url.pathname === "/api/v1/tasks") return json({ items: [], total: 0, page: 1, page_size: Number(url.searchParams.get("page_size") || 20) });
    if (url.pathname === "/api/v1/presets") return json(presets);
    return new Response(JSON.stringify({ detail: "Not found" }), { status: 404, headers: { "Content-Type": "application/json" } });
  });
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

beforeEach(() => {
  localStorage.clear();
});

afterEach(() => {
  vi.useRealTimers();
});

describe("workspace shell and staged creation", () => {
  test("locks the title and mode while the first draft request is pending", async () => {
    let resolveCreate!: (response: Response) => void;
    const createResponse = new Promise<Response>((resolve) => { resolveCreate = resolve; });
    installBaseFetch((url, init) => {
      if (url.pathname === "/api/v1/tasks" && init?.method === "POST") return createResponse;
    });
    vi.stubGlobal("XMLHttpRequest", class {
      upload = { addEventListener: () => undefined };
      open() {}
      addEventListener() {}
      send() {}
    });
    const user = userEvent.setup();
    renderAt("/workspace/new");
    const title = await screen.findByLabelText("任务标题");
    await user.type(title, "训练 A");
    await user.upload(screen.getByLabelText("注册视频"), new File(["video"], "enroll.mp4", { type: "video/mp4" }));

    expect(title).toBeDisabled();
    expect(screen.getByRole("radio", { name: /快速/ })).toBeDisabled();
    resolveCreate(json(task({ title: "训练 A" }), { status: 201 }));
  });

  test("enforces the 120-code-point title boundary and localizes a first-upload 422", async () => {
    const fetchMock = installBaseFetch((url, init) => {
      if (url.pathname === "/api/v1/tasks" && init?.method === "POST") return new Response(JSON.stringify({ detail: [{ loc: ["body", "title"], type: "string_too_long", msg: "String should have at most 120 characters" }] }), { status: 422, headers: { "Content-Type": "application/json" } });
    });
    vi.stubGlobal("XMLHttpRequest", class {
      upload = { addEventListener: () => undefined };
      open() {}
      addEventListener() {}
      send() { throw new Error("upload must not start after draft validation fails"); }
    });
    const user = userEvent.setup();
    renderAt("/workspace/new");
    const title = await screen.findByLabelText("任务标题");
    expect(title).toBeRequired();
    expect(title).not.toHaveAttribute("maxlength");
    await user.upload(screen.getByLabelText("注册视频"), new File(["video"], "missing-title.mp4", { type: "video/mp4" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("请输入任务标题");
    expect(fetchMock.mock.calls.filter(([input, init]) => String(input).endsWith("/api/v1/tasks") && init?.method === "POST")).toHaveLength(0);
    fireEvent.change(title, { target: { value: "🏀".repeat(121) } });
    await user.upload(screen.getByLabelText("注册视频"), new File(["video"], "too-long.mp4", { type: "video/mp4" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("任务标题不能超过 120 个字符");
    expect(fetchMock.mock.calls.filter(([input, init]) => String(input).endsWith("/api/v1/tasks") && init?.method === "POST")).toHaveLength(0);

    fireEvent.change(title, { target: { value: "🏀".repeat(120) } });
    await user.upload(screen.getByLabelText("注册视频"), new File(["video"], "boundary.mp4", { type: "video/mp4" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("任务标题不能超过 120 个字符");
    expect(title).toBeEnabled();
    expect(fetchMock.mock.calls.filter(([input, init]) => String(input).endsWith("/api/v1/tasks") && init?.method === "POST")).toHaveLength(1);
  });

  test("expires the authenticated session when a normal request returns 401", async () => {
    const fetchMock = installBaseFetch((url) => {
      if (url.pathname === "/api/v1/account/usage") return new Response(JSON.stringify({ detail: "Not authenticated" }), { status: 401, headers: { "Content-Type": "application/json" } });
    });
    renderAt("/workspace/settings");
    await waitFor(() => expect(screen.getByTestId("workspace-location")).toHaveTextContent("/login?next=%2Fworkspace%2Fsettings"));
    expect(fetchMock.mock.calls.filter(([input]) => String(input).endsWith("/api/v1/users/me"))).toHaveLength(1);
  });

  test("expires the authenticated session when an upload returns 401", async () => {
    const fetchMock = installBaseFetch((url, init) => {
      if (url.pathname === "/api/v1/tasks" && init?.method === "POST") return json(task({ title: "训练 A" }), { status: 201 });
    });
    class UnauthorizedXhr {
      status = 0;
      responseText = "";
      upload = { addEventListener: () => undefined };
      listeners = new Map<string, () => void>();
      open() {}
      addEventListener(event: string, listener: () => void) { this.listeners.set(event, listener); }
      send() { this.status = 401; this.responseText = JSON.stringify({ detail: "Not authenticated" }); queueMicrotask(() => this.listeners.get("load")?.()); }
    }
    vi.stubGlobal("XMLHttpRequest", UnauthorizedXhr);
    const user = userEvent.setup();
    renderAt("/workspace/new");
    await user.type(await screen.findByLabelText("任务标题"), "训练 A");
    await user.upload(screen.getByLabelText("注册视频"), new File(["video"], "enroll.mp4", { type: "video/mp4" }));
    await waitFor(() => expect(screen.getByTestId("workspace-location")).toHaveTextContent("/login?next=%2Fworkspace%2Fnew"));
    expect(fetchMock.mock.calls.filter(([input]) => String(input).endsWith("/api/v1/users/me"))).toHaveLength(1);
  });

  test("uses the persisted locale for upload labels on the first protected render", async () => {
    document.documentElement.lang = "zh";
    localStorage.setItem("dashanbing-locale", "en");
    installBaseFetch();
    renderAt("/workspace/new");

    expect(await screen.findByRole("heading", { name: "Create analysis task" })).toBeVisible();
    expect(screen.getByLabelText("Enrollment video")).toBeVisible();
    expect(screen.queryByLabelText("注册视频")).not.toBeInTheDocument();
  });

  test("keeps every phone drawer action in the focus loop and closes from utility navigation", async () => {
    vi.stubGlobal("matchMedia", vi.fn().mockImplementation((query: string) => ({
      matches: query === "(max-width: 760px)", media: query, onchange: null,
      addEventListener: vi.fn(), removeEventListener: vi.fn(), addListener: vi.fn(), removeListener: vi.fn(), dispatchEvent: vi.fn(),
    })));
    installBaseFetch();
    const user = userEvent.setup();
    renderAt("/workspace/new");
    const menu = await screen.findByRole("button", { name: "打开工作台菜单" });
    await user.click(menu);
    const drawer = screen.getByRole("dialog", { name: "工作台导航" });
    const create = within(drawer).getByRole("link", { name: "创建任务" });
    const home = within(drawer).getByRole("link", { name: "大山冰首页" });
    const close = within(drawer).getByRole("button", { name: "关闭工作台菜单" });
    const settings = within(drawer).getByRole("link", { name: "设置" });

    expect(create).toHaveFocus();
    await user.keyboard("{Shift>}{Tab}{/Shift}");
    expect(close).toHaveFocus();
    await user.keyboard("{Shift>}{Tab}{/Shift}");
    expect(home).toHaveFocus();
    await user.keyboard("{Shift>}{Tab}{/Shift}");
    expect(settings).toHaveFocus();
    await user.keyboard("{Tab}");
    expect(home).toHaveFocus();
    await user.keyboard("{Tab}");
    expect(close).toHaveFocus();
    await user.click(close);
    expect(screen.queryByRole("dialog", { name: "工作台导航" })).not.toBeInTheDocument();
    await waitFor(() => expect(menu).toHaveFocus());

    await user.click(menu);
    const api = within(screen.getByRole("dialog", { name: "工作台导航" })).getByRole("link", { name: "API" });
    api.addEventListener("click", (event) => event.preventDefault(), { once: true });
    await user.click(api);
    expect(screen.queryByRole("dialog", { name: "工作台导航" })).not.toBeInTheDocument();
    expect(screen.getByTestId("workspace-location")).toHaveTextContent("/workspace/new");
    await waitFor(() => expect(menu).toHaveFocus());

    await user.click(menu);
    await user.click(within(screen.getByRole("dialog", { name: "工作台导航" })).getByRole("link", { name: "设置" }));
    await waitFor(() => expect(screen.getByTestId("workspace-location")).toHaveTextContent("/workspace/settings"));
    expect(screen.queryByRole("dialog", { name: "工作台导航" })).not.toBeInTheDocument();
    await waitFor(() => expect(menu).toHaveFocus());
    await user.click(screen.getByRole("button", { name: "English" }));
    await user.click(menu);
    const englishClose = within(screen.getByRole("dialog", { name: "Workspace navigation" })).getByRole("button", { name: "Close workspace menu" });
    expect(englishClose).toBeVisible();
    await user.click(englishClose);
    await waitFor(() => expect(menu).toHaveFocus());
  });

  test("serializes slot writes to match the backend draft upload state machine", async () => {
    const uploaded: Array<{ slot: string; original_filename: string; byte_size: number; validation_state: string; created_at: string; updated_at: string }> = [];
    installBaseFetch((url, init) => {
      if (url.pathname === "/api/v1/tasks" && init?.method === "POST") return json(task(), { status: 201 });
    });

    let activeWrites = 0;
    let maxActiveWrites = 0;
    const pending: Array<{ xhr: FakeXhr; slot: string; file: File }> = [];
    class FakeXhr {
      url = "";
      status = 0;
      responseText = "";
      upload = { addEventListener: () => undefined };
      listeners = new Map<string, () => void>();
      open(_method: string, url: string) { this.url = url; }
      addEventListener(event: string, listener: () => void) { this.listeners.set(event, listener); }
      send(body: FormData) {
        activeWrites += 1;
        maxActiveWrites = Math.max(maxActiveWrites, activeWrites);
        pending.push({ xhr: this, slot: this.url.split("/").at(-1)!, file: body.get("file") as File });
      }
      finish() {
        const item = pending.shift()!;
        activeWrites -= 1;
        uploaded.push({ slot: item.slot, original_filename: item.file.name, byte_size: item.file.size, validation_state: "valid", created_at: "2026-09-05T01:00:00Z", updated_at: "2026-09-05T01:00:00Z" });
        this.status = 200;
        this.responseText = JSON.stringify(task({ inputs: [...uploaded] }));
        this.listeners.get("load")?.();
      }
    }
    vi.stubGlobal("XMLHttpRequest", FakeXhr);

    const user = userEvent.setup();
    renderAt("/workspace/new");
    await screen.findByRole("heading", { name: "创建分析任务" });
    await user.type(screen.getByLabelText("任务标题"), "训练 A");
    await user.upload(screen.getByLabelText("注册视频"), new File(["enroll"], "enroll.mp4", { type: "video/mp4" }));
    await user.upload(screen.getByLabelText("机位 1"), new File(["cam1"], "cam1.mp4", { type: "video/mp4" }));
    await flushPromises();

    expect(pending).toHaveLength(1);
    expect(maxActiveWrites).toBe(1);
    pending[0].xhr.finish();
    await flushPromises();
    expect(pending).toHaveLength(1);
    expect(maxActiveWrites).toBe(1);
    pending[0].xhr.finish();
    await waitFor(() => expect(screen.getByText("cam1.mp4")).toBeVisible());
  });

  test("renders the scoped shell and recovers a failed slot before enabling explicit submit", async () => {
    const uploaded = new Map<string, { slot: string; original_filename: string; byte_size: number; validation_state: string; created_at: string; updated_at: string }>();
    let camOneAttempts = 0;
    let created = false;
    const fetchMock = installBaseFetch((url, init) => {
      if (url.pathname === "/api/v1/tasks" && init?.method === "POST") {
        created = true;
        return json(task(), { status: 201 });
      }
      if (url.pathname === "/api/v1/tasks/task-1/submit") {
        return json(task({ status: "queued", inputs: [...uploaded.values()] }));
      }
    });

    class FakeXhr {
      method = "";
      url = "";
      status = 0;
      responseText = "";
      upload = { addEventListener: (_event: string, listener: (event: ProgressEvent) => void) => { this.progress = listener; } };
      progress?: (event: ProgressEvent) => void;
      listeners = new Map<string, () => void>();
      open(method: string, url: string) { this.method = method; this.url = url; }
      addEventListener(event: string, listener: () => void) { this.listeners.set(event, listener); }
      setRequestHeader() {}
      send(body: FormData) {
        const slot = this.url.split("/").at(-1)!;
        const file = body.get("file") as File;
        this.progress?.({ lengthComputable: true, loaded: file.size / 2, total: file.size } as ProgressEvent);
        queueMicrotask(() => {
          if (slot === "cam_01" && camOneAttempts++ === 0) {
            this.status = 400;
            this.responseText = JSON.stringify({ detail: "Invalid video" });
          } else {
            uploaded.set(slot, { slot, original_filename: file.name, byte_size: file.size, validation_state: "valid", created_at: "2026-09-05T01:00:00Z", updated_at: "2026-09-05T01:00:00Z" });
            this.status = 200;
            this.responseText = JSON.stringify(task({ inputs: [...uploaded.values()] }));
          }
          this.listeners.get("load")?.();
        });
      }
    }
    vi.stubGlobal("XMLHttpRequest", FakeXhr);

    const user = userEvent.setup();
    renderAt("/workspace/new");

    expect(await screen.findByRole("heading", { name: "创建分析任务" })).toBeVisible();
    const shellNav = screen.getByRole("navigation", { name: "工作台导航" });
    expect(within(shellNav).getByRole("link", { name: "创建任务" })).toHaveAttribute("href", "/workspace/new");
    expect(within(shellNav).getByRole("link", { name: "任务列表" })).toHaveAttribute("href", "/workspace/tasks");
    expect(screen.getByRole("link", { name: "GitHub" })).toHaveAttribute("href", "https://github.com/Siyuan-Xue/dashanbing-backend");
    expect(screen.getByRole("link", { name: "API" })).toHaveAttribute("href", "/api/docs");
    expect(screen.queryByText(/合集|客户端|下载|促销/)).not.toBeInTheDocument();
    expect(await screen.findAllByTestId("preset-card")).toHaveLength(4);

    const submit = screen.getByRole("button", { name: "提交分析" });
    expect(submit).toBeDisabled();
    await user.type(screen.getByLabelText("任务标题"), "周三投篮训练");
    await user.upload(screen.getByLabelText("注册视频"), new File(["enroll"], "enroll.mp4", { type: "video/mp4" }));
    await user.upload(screen.getByLabelText("机位 1"), new File(["cam1"], "cam1.mp4", { type: "video/mp4" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Invalid video");
    expect(submit).toBeDisabled();

    await user.click(screen.getByRole("button", { name: "重试机位 1" }));
    await waitFor(() => expect(screen.getByText("cam1.mp4")).toBeVisible());
    await user.upload(screen.getByLabelText("机位 1"), new File(["new-cam1"], "cam1-replaced.mp4", { type: "video/mp4" }));
    await waitFor(() => expect(screen.getByText("cam1-replaced.mp4")).toBeVisible());
    expect(screen.queryByText("cam1.mp4")).not.toBeInTheDocument();

    await user.upload(screen.getByLabelText("机位 2"), new File(["cam2"], "cam2.mp4", { type: "video/mp4" }));
    await user.upload(screen.getByLabelText("机位 3"), new File(["cam3"], "cam3.mp4", { type: "video/mp4" }));
    await user.upload(screen.getByLabelText("机位 4"), new File(["cam4"], "cam4.mp4", { type: "video/mp4" }));
    await waitFor(() => expect(submit).toBeEnabled());
    expect(created).toBe(true);

    await user.click(submit);
    await waitFor(() => expect(screen.getByTestId("workspace-location")).toHaveTextContent("/workspace/tasks/task-1"));
    expect(fetchMock).toHaveBeenCalledWith("/api/v1/tasks/task-1/submit", expect.objectContaining({ method: "POST", credentials: "include" }));
  });
});

describe("task list workflows", () => {
  test("re-queries filtered rows after lifecycle success and state conflict", async () => {
    let failedStatus = "failed";
    let queuedStatus = "queued";
    let retryCalls = 0;
    installBaseFetch((url) => {
      if (url.pathname === "/api/v1/tasks" && url.searchParams.get("page_size") !== "5") {
        const filter = url.searchParams.get("status");
        const items = filter === "failed" && failedStatus === "failed" ? [task({ id: "failed-1", status: "failed" })]
          : filter === "queued" && queuedStatus === "queued" ? [task({ id: "queued-1", status: "queued" })] : [];
        return json({ items, total: items.length, page: 1, page_size: 10 });
      }
      if (url.pathname === "/api/v1/tasks/failed-1/retry") {
        retryCalls += 1;
        failedStatus = "queued";
        if (retryCalls === 1) return json(task({ id: "failed-1", status: "queued" }));
        return new Response(JSON.stringify({ detail: "Task state changed" }), { status: 409, headers: { "Content-Type": "application/json" } });
      }
      if (url.pathname === "/api/v1/tasks/queued-1/cancel") {
        queuedStatus = "canceled";
        return json(task({ id: "queued-1", status: "canceled" }));
      }
    });
    const user = userEvent.setup();
    const first = renderAt("/workspace/tasks?status=failed&page=1&page_size=10");
    await user.click(await screen.findByRole("button", { name: "重试周三投篮训练" }));
    await user.click(within(screen.getByRole("dialog")).getByRole("button", { name: "确认重试" }));
    expect(await screen.findByText("没有符合条件的任务")).toBeVisible();
    first.unmount();

    const second = renderAt("/workspace/tasks?status=queued&page=1&page_size=10");
    await user.click(await screen.findByRole("button", { name: "取消周三投篮训练" }));
    await user.click(within(screen.getByRole("dialog")).getByRole("button", { name: "确认取消" }));
    expect(await screen.findByText("没有符合条件的任务")).toBeVisible();
    second.unmount();

    failedStatus = "failed";
    renderAt("/workspace/tasks?status=failed&page=1&page_size=10");
    await user.click(await screen.findByRole("button", { name: "重试周三投篮训练" }));
    failedStatus = "queued";
    await user.click(within(screen.getByRole("dialog")).getByRole("button", { name: "确认重试" }));
    expect(await screen.findByText("没有符合条件的任务")).toBeVisible();
  });

  test("moves to the previous page after deleting the only row on a later page", async () => {
    let deleted = false;
    installBaseFetch((url, init) => {
      if (url.pathname === "/api/v1/tasks/last-row" && init?.method === "DELETE") { deleted = true; return new Response(null, { status: 204 }); }
      if (url.pathname === "/api/v1/tasks" && url.searchParams.get("page_size") !== "5") {
        const page = Number(url.searchParams.get("page") || 1);
        if (page === 2 && !deleted) return json({ items: [task({ id: "last-row", status: "completed" })], total: 11, page: 2, page_size: 10 });
        return json({ items: [task({ id: "page-one", title: "第一页任务", status: "completed" })], total: 10, page: 1, page_size: 10 });
      }
    });
    const user = userEvent.setup();
    renderAt("/workspace/tasks?page=2&page_size=10");
    await user.click(await screen.findByRole("button", { name: "删除周三投篮训练" }));
    await user.click(within(screen.getByRole("dialog")).getByRole("button", { name: "确认删除" }));

    await waitFor(() => expect(screen.getByTestId("workspace-location")).toHaveTextContent("/workspace/tasks?page=1&page_size=10"));
    expect(await screen.findByText("第一页任务")).toBeVisible();
  });

  test("synchronizes filter controls when browser history changes the URL", async () => {
    installBaseFetch();
    const user = userEvent.setup();
    renderHistory([
      "/workspace/tasks?q=first&status=failed&mode=full&page=1&page_size=10",
      "/workspace/tasks?q=second&status=queued&mode=quick&page=2&page_size=10",
    ], 1);
    expect(await screen.findByRole("searchbox", { name: "搜索任务" })).toHaveValue("second");
    expect(screen.getByLabelText("状态")).toHaveValue("queued");
    await user.click(screen.getByRole("button", { name: "History back" }));
    await waitFor(() => expect(screen.getByRole("searchbox", { name: "搜索任务" })).toHaveValue("first"));
    expect(screen.getByLabelText("状态")).toHaveValue("failed");
    expect(screen.getByLabelText("分析模式")).toHaveValue("full");
  });

  test("contains modal focus, closes on Escape, and restores the trigger", async () => {
    installBaseFetch((url) => {
      if (url.pathname === "/api/v1/tasks" && url.searchParams.get("page_size") !== "5") return json({ items: [task({ id: "failed-1", status: "failed" })], total: 1, page: 1, page_size: 10 });
    });
    const user = userEvent.setup();
    renderAt("/workspace/tasks");
    const trigger = await screen.findByRole("button", { name: "重试周三投篮训练" });
    await user.click(trigger);
    const dialog = screen.getByRole("dialog", { name: "重试任务" });
    expect(dialog).toHaveAttribute("aria-describedby", "confirm-message");
    const cancel = within(dialog).getByRole("button", { name: "返回" });
    const confirm = within(dialog).getByRole("button", { name: "确认重试" });
    expect(cancel).toHaveFocus();
    trigger.focus();
    await user.keyboard("{Tab}");
    expect(cancel).toHaveFocus();
    await user.keyboard("{Shift>}{Tab}{/Shift}");
    expect(confirm).toHaveFocus();
    await user.keyboard("{Tab}");
    expect(cancel).toHaveFocus();
    await user.keyboard("{Escape}");
    expect(dialog).not.toBeInTheDocument();
    expect(trigger).toHaveFocus();
  });

  test("syncs filters and paging to the task query and confirms lifecycle actions", async () => {
    const failed = task({ id: "failed-1", status: "failed", error_message: "GPU unavailable" });
    const fetchMock = installBaseFetch((url, init) => {
      if (url.pathname === "/api/v1/tasks/failed-1/retry") return json(task({ id: "failed-1", status: "queued" }));
      if (url.pathname === "/api/v1/tasks" && !init?.method) return json({ items: [failed], total: 21, page: Number(url.searchParams.get("page") || 1), page_size: Number(url.searchParams.get("page_size") || 10) });
    });
    const user = userEvent.setup();
    renderAt("/workspace/tasks");

    await screen.findByRole("heading", { name: "任务列表" });
    await user.type(screen.getByRole("searchbox", { name: "搜索任务" }), "周三");
    await user.selectOptions(screen.getByLabelText("状态"), "failed");
    await user.selectOptions(screen.getByLabelText("分析模式"), "quick");
    await user.click(screen.getByRole("button", { name: "筛选" }));
    await waitFor(() => expect(screen.getByTestId("workspace-location")).toHaveTextContent("q=%E5%91%A8%E4%B8%89&status=failed&mode=quick&page=1&page_size=10"));
    await user.click(screen.getByRole("button", { name: "下一页" }));
    await waitFor(() => expect(screen.getByTestId("workspace-location")).toHaveTextContent("page=2"));

    await user.click(screen.getByRole("button", { name: "重试周三投篮训练" }));
    const dialog = await screen.findByRole("dialog", { name: "重试任务" });
    await user.click(within(dialog).getByRole("button", { name: "确认重试" }));
    await waitFor(() => expect(fetchMock).toHaveBeenCalledWith("/api/v1/tasks/failed-1/retry", expect.objectContaining({ method: "POST" })));
  });

  test("requires confirmation before cancel and delete and applies the returned lifecycle", async () => {
    let current: ReturnType<typeof task> | null = task({ id: "queued-1", status: "queued", progress: 12 });
    const fetchMock = installBaseFetch((url, init) => {
      if (url.pathname === "/api/v1/tasks" && !init?.method) return json({ items: current ? [current] : [], total: current ? 1 : 0, page: 1, page_size: 10 });
      if (url.pathname === "/api/v1/tasks/queued-1/cancel") {
        current = task({ id: "queued-1", status: "canceled", progress: 12 });
        return json(current);
      }
      if (url.pathname === "/api/v1/tasks/queued-1" && init?.method === "DELETE") { current = null; return new Response(null, { status: 204 }); }
    });
    const user = userEvent.setup();
    renderAt("/workspace/tasks");

    await user.click(await screen.findByRole("button", { name: "取消周三投篮训练" }));
    expect(fetchMock).not.toHaveBeenCalledWith("/api/v1/tasks/queued-1/cancel", expect.anything());
    await user.click(within(screen.getByRole("dialog", { name: "取消任务" })).getByRole("button", { name: "确认取消" }));
    expect(await screen.findByRole("button", { name: "删除周三投篮训练" })).toBeVisible();

    await user.click(screen.getByRole("button", { name: "删除周三投篮训练" }));
    expect(fetchMock).not.toHaveBeenCalledWith("/api/v1/tasks/queued-1", expect.objectContaining({ method: "DELETE" }));
    await user.click(within(screen.getByRole("dialog", { name: "删除任务" })).getByRole("button", { name: "确认删除" }));
    expect(await screen.findByText("没有符合条件的任务")).toBeVisible();
  });
});

describe("task and example result workspaces", () => {
  test("clears task A result immediately when same-route navigation starts task B and aborts both requests", async () => {
    let resolveB!: (response: Response) => void;
    const deferredB = new Promise<Response>((resolve) => { resolveB = resolve; });
    let signalA: AbortSignal | undefined;
    let signalAResult: AbortSignal | undefined;
    let signalB: AbortSignal | undefined;
    installBaseFetch((url, init) => {
      if (url.pathname === "/api/v1/tasks" && url.searchParams.get("page_size") === "5") return json({ items: [task({ id: "task-b", title: "任务 B", status: "queued" })], total: 1, page: 1, page_size: 5 });
      if (url.pathname === "/api/v1/tasks/task-a") { signalA = init?.signal || undefined; return json(task({ id: "task-a", title: "任务 A", status: "completed", progress: 100 })); }
      if (url.pathname === "/api/v1/tasks/task-a/result") { signalAResult = init?.signal || undefined; return json(productResult); }
      if (url.pathname === "/api/v1/tasks/task-b") { signalB = init?.signal || undefined; return deferredB; }
    });
    const user = userEvent.setup();
    const rendered = renderAt("/workspace/tasks/task-a");
    expect(await screen.findByRole("link", { name: "下载 JSON 结果" })).toBeVisible();
    await user.click(screen.getByRole("link", { name: "任务 B" }));

    expect(screen.queryByRole("link", { name: "下载 JSON 结果" })).not.toBeInTheDocument();
    expect(screen.queryByTitle("阶段合成播放器")).not.toBeInTheDocument();
    expect(screen.getByRole("status", { name: "正在加载任务" })).toBeVisible();
    expect(signalA?.aborted).toBe(true);
    expect(signalAResult?.aborted).toBe(true);
    resolveB(json(task({ id: "task-b", title: "任务 B", status: "queued", stage_message: "等待执行" })));
    expect(await screen.findByRole("heading", { name: "任务 B" })).toBeVisible();
    rendered.unmount();
    expect(signalB?.aborted).toBe(true);
  });

  test("aborts the prior detail generation before retrying a failed result", async () => {
    let resultCalls = 0;
    let firstSignal: AbortSignal | undefined;
    let secondSignal: AbortSignal | undefined;
    const pendingResult = new Promise<Response>(() => {});
    installBaseFetch((url, init) => {
      if (url.pathname === "/api/v1/tasks/task-1") return json(task({ status: "completed", progress: 100 }));
      if (url.pathname === "/api/v1/tasks/task-1/result") {
        resultCalls += 1;
        if (resultCalls === 1) { firstSignal = init?.signal || undefined; return new Response(JSON.stringify({ detail: "Result unavailable" }), { status: 503, headers: { "Content-Type": "application/json" } }); }
        secondSignal = init?.signal || undefined;
        return pendingResult;
      }
    });
    const user = userEvent.setup();
    const rendered = renderAt("/workspace/tasks/task-1");
    await user.click(await screen.findByRole("button", { name: "重试" }));
    await waitFor(() => expect(resultCalls).toBe(2));
    expect(firstSignal?.aborted).toBe(true);
    rendered.unmount();
    expect(secondSignal?.aborted).toBe(true);
  });

  test("does not schedule another poll when an active task response arrives after unmount", async () => {
    vi.useFakeTimers({ toFake: ["setTimeout", "clearTimeout"] });
    let resolveDetail!: (response: Response) => void;
    const deferredDetail = new Promise<Response>((resolve) => { resolveDetail = resolve; });
    let detailCalls = 0;
    installBaseFetch((url) => {
      if (url.pathname === "/api/v1/tasks/task-1") {
        detailCalls += 1;
        return deferredDetail;
      }
    });

    const rendered = renderAt("/workspace/tasks/task-1");
    await flushPromises();
    expect(detailCalls).toBe(1);
    rendered.unmount();
    resolveDetail(json(task({ status: "queued", progress: 10 })));
    await flushPromises();
    await act(async () => { await vi.advanceTimersByTimeAsync(4000); });

    expect(detailCalls).toBe(1);
  });

  test("polls active tasks until terminal, then shows media, result tabs, and download", async () => {
    vi.useFakeTimers({ toFake: ["setTimeout", "clearTimeout"] });
    let detailCalls = 0;
    const fetchMock = installBaseFetch((url) => {
      if (url.pathname === "/api/v1/tasks/task-1") {
        detailCalls += 1;
        if (detailCalls === 1) return json(task({ status: "queued", progress: 10, stage_message: "等待执行" }));
        if (detailCalls === 2) return json(task({ status: "running", progress: 62, stage_message: "分析动作" }));
        return json(task({ status: "completed", progress: 100, completed_at: "2026-09-05T02:00:00Z" }));
      }
      if (url.pathname === "/api/v1/tasks/task-1/result") return json(productResult);
    });
    renderAt("/workspace/tasks/task-1");

    await flushPromises();
    expect(screen.getAllByText("等待执行").length).toBeGreaterThan(0);
    await act(async () => { await vi.advanceTimersByTimeAsync(2000); });
    await flushPromises();
    expect(screen.getAllByText("分析动作").length).toBeGreaterThan(0);
    await act(async () => { await vi.advanceTimersByTimeAsync(2000); });
    await flushPromises();
    expect(screen.getByText("60%")).toBeVisible();
    expect(screen.getByRole("tab", { name: "阶段合成" })).toHaveAttribute("aria-selected", "true");
    fireEvent.click(screen.getByRole("tab", { name: "机位 1" }));
    expect(screen.getByTitle("机位 1 播放器")).toHaveAttribute("src", "/api/v1/tasks/task-1/media/cam_01");
    expect(screen.getByRole("link", { name: "下载 JSON 结果" })).toHaveAttribute("href", "/api/v1/tasks/task-1/result");

    const stoppedAt = detailCalls;
    await act(async () => { await vi.advanceTimersByTimeAsync(8000); });
    expect(detailCalls).toBe(stoppedAt);
    expect(fetchMock).toHaveBeenCalledWith("/api/v1/tasks/task-1/result", expect.objectContaining({ credentials: "include" }));
  });

  test("reuses the result workspace for presets and executes the selected preset", async () => {
    const fetchMock = installBaseFetch((url, init) => {
      if (url.pathname === "/api/v1/presets/quick-demo/result") return json({ ...productResult, media: { phases: "/api/v1/presets/quick-demo/media/phases" } });
      if (url.pathname === "/api/v1/tasks/from-preset" && init?.method === "POST") return json(task({ id: "preset-task", preset_id: "quick-demo", status: "queued" }), { status: 201 });
    });
    const user = userEvent.setup();
    renderAt("/workspace/examples/quick-demo");

    expect(await screen.findByRole("heading", { name: "快速演示" })).toBeVisible();
    expect(screen.getByText("4 次跳投")).toBeVisible();
    await user.selectOptions(screen.getByLabelText("分析模式"), "full");
    await user.click(screen.getByRole("button", { name: "用此示例创建任务" }));
    await waitFor(() => expect(screen.getByTestId("workspace-location")).toHaveTextContent("/workspace/tasks/preset-task"));
    const call = fetchMock.mock.calls.find(([input]) => String(input).endsWith("/api/v1/tasks/from-preset"));
    expect(JSON.parse(String(call?.[1]?.body))).toEqual({ preset_id: "quick-demo", mode: "full" });
  });

  test.each([
    ["draft", "任务尚未提交，可继续补充或替换视频。"],
    ["uploading", "正在验证上传的视频，请等待当前文件完成。"],
    ["queued", "任务已进入后台队列，可以离开页面后稍后回来。"],
    ["running", "正在分析视频，进度会自动更新。"],
    ["completed", "任务完成，但当前没有可展示的结果。"],
    ["failed", "任务未完成，请查看错误后重试。"],
    ["canceled", "任务已取消，可以从任务列表重新运行。"],
    ["expired", "草稿已过期，请创建新任务。"],
  ] as const)("shows an explicit %s empty-result message", (status, expected) => {
    installBaseFetch();
    render(<MemoryRouter><LocaleProvider><ResultWorkspace task={task({ status }) as Task} result={null}/></LocaleProvider></MemoryRouter>);
    expect(screen.getByText(expected)).toBeVisible();
  });

  test("localizes preset, task metadata, action, and outcome identifiers without changing API values", async () => {
    localStorage.setItem("dashanbing-locale", "en");
    installBaseFetch((url) => {
      if (url.pathname === "/api/v1/tasks/task-1") return json(task({ status: "completed", mode: "quick", source_type: "upload", progress: 100, completed_at: "2026-09-04T01:03:00Z" }));
      if (url.pathname === "/api/v1/tasks/task-1/result") return json(productResult);
    });
    const user = userEvent.setup();
    const detail = renderAt("/workspace/tasks/task-1");
    expect(await screen.findAllByText("Completed")).toHaveLength(2);
    expect(screen.queryByText("completed")).not.toBeInTheDocument();
    expect(screen.getByText("Quick")).toBeVisible();
    expect(screen.getByText("Upload")).toBeVisible();
    await user.click(screen.getByRole("tab", { name: "Timeline" }));
    expect(screen.getByText("Jump shot")).toBeVisible();
    expect(screen.getByText(/Made/)).toBeVisible();
    detail.unmount();

    const newTask = renderAt("/workspace/new");
    const cards = await screen.findAllByTestId("preset-card");
    expect(within(cards[0]).getByRole("heading", { name: "Quick demo" })).toBeVisible();
    expect(within(cards[0]).getByText("4 jump shots")).toBeVisible();
    expect(within(cards[0]).getByText(/9.4 MIN · Quick/)).toBeVisible();
    expect(within(cards[1]).getByRole("heading", { name: "Mixed actions" })).toBeVisible();
    expect(within(cards[1]).getByText("Triple threat and jump shots")).toBeVisible();
    expect(within(cards[1]).getByText(/26.7 MIN · Full/)).toBeVisible();
    expect(within(cards[2]).getByRole("heading", { name: "Verified outcomes" })).toBeVisible();
    expect(within(cards[2]).getByText("Free throws with verified shot outcomes")).toBeVisible();
    expect(within(cards[2]).getByText(/30.9 MIN · Verified/)).toBeVisible();
    expect(within(cards[3]).getByRole("heading", { name: "Layup demo" })).toBeVisible();
    expect(within(cards[3]).getByText("6 layups")).toBeVisible();
    expect(within(cards[3]).getByText(/14.3 MIN · Layup/)).toBeVisible();
    expect(screen.queryByText("快速演示")).not.toBeInTheDocument();
    newTask.unmount();

    renderAt("/workspace/tasks");
    expect(await screen.findByRole("heading", { name: "Tasks" })).toBeVisible();
    expect(screen.getByRole("option", { name: "Failed" })).toHaveValue("failed");
    expect(screen.getByRole("option", { name: "Quick" })).toHaveValue("quick");
  });

  test("localizes known worker stage messages while preserving unknown backend detail", async () => {
    installBaseFetch((url) => {
      if (url.pathname === "/api/v1/tasks/task-1") return json(task({ status: "completed", progress: 100, stage_message: "Complete", completed_at: "2026-09-04T01:03:00Z" }));
      if (url.pathname === "/api/v1/tasks/task-1/result") return json(productResult);
    });
    renderAt("/workspace/tasks/task-1");

    await waitFor(() => expect(document.querySelector(".detail-progress small")).toHaveTextContent("已完成"));
    expect(document.querySelector(".detail-progress small")).not.toHaveTextContent("Complete");
    expect(taskStageMessageLabel("zh", "Worker handoff 7/9")).toBe("Worker handoff 7/9");
  });
});

describe("workspace settings", () => {
  test("shows only real quota and retention data and updates locale and theme", async () => {
    installBaseFetch((url) => {
      if (url.pathname === "/api/v1/account/usage") return json({
        submitted_today: { used: 4, limit: 20 }, unfinished_tasks: { used: 2, limit: 5 }, drafts: { used: 1, limit: 3 }, active_api_keys: { used: 2, limit: 5 },
        retention: { drafts: "24 hours", enrollment_data: "7 days", raw_inputs: "30 days", results: "180 days" },
      });
    });
    const user = userEvent.setup();
    renderAt("/workspace/settings");

    expect(await screen.findByRole("heading", { name: "设置" })).toBeVisible();
    expect(await screen.findByText("4 / 20")).toBeVisible();
    expect(screen.getByText("180 days")).toBeVisible();
    expect(screen.queryByText(/账单|团队|Webhook|对象存储/)).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "English" }));
    expect(screen.getByRole("heading", { name: "Settings" })).toBeVisible();
    await user.click(screen.getByRole("button", { name: "Switch to dark theme" }));
    expect(document.documentElement).toHaveAttribute("data-theme", "dark");
  });
});
