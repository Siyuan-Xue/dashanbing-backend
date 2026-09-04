import { act } from "react";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, useLocation } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";

import App from "./App";
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
  return <output data-testid="workspace-location">{location.pathname}{location.search}</output>;
}

function renderAt(path: string) {
  return render(<MemoryRouter initialEntries={[path]}><App/><LocationProbe/></MemoryRouter>);
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
  test("uses the persisted locale for upload labels on the first protected render", async () => {
    document.documentElement.lang = "zh";
    localStorage.setItem("dashanbing-locale", "en");
    installBaseFetch();
    renderAt("/workspace/new");

    expect(await screen.findByRole("heading", { name: "Create analysis task" })).toBeVisible();
    expect(screen.getByLabelText("Enrollment video")).toBeVisible();
    expect(screen.queryByLabelText("注册视频")).not.toBeInTheDocument();
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
    let current = task({ id: "queued-1", status: "queued", progress: 12 });
    const fetchMock = installBaseFetch((url, init) => {
      if (url.pathname === "/api/v1/tasks" && !init?.method) return json({ items: [current], total: 1, page: 1, page_size: 10 });
      if (url.pathname === "/api/v1/tasks/queued-1/cancel") {
        current = task({ id: "queued-1", status: "canceled", progress: 12 });
        return json(current);
      }
      if (url.pathname === "/api/v1/tasks/queued-1" && init?.method === "DELETE") return new Response(null, { status: 204 });
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
