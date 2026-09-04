import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";

import App from "./App";
import "./styles.css";

const user = { id: 7, username: "coach", email: "coach@example.com", is_active: true };
const usage = {
  submitted_today: { used: 4, limit: 20 }, unfinished_tasks: { used: 2, limit: 5 },
  drafts: { used: 1, limit: 3 }, active_api_keys: { used: 2, limit: 5 },
  retention: { drafts: "24 hours", enrollment_data: "7 days", raw_inputs: "30 days", results: "180 days" },
};
const keys = [
  { id: "active", name: "Production", prefix: "dsb_live_abcd12", last_four: "9xyz", status: "active", created_at: "2026-09-01T10:00:00Z", expires_at: "2026-12-01T10:00:00Z", last_used_at: null, revoked_at: null },
  { id: "expired", name: "Old runner", prefix: "dsb_live_old123", last_four: "0old", status: "expired", created_at: "2026-01-01T10:00:00Z", expires_at: "2026-04-01T10:00:00Z", last_used_at: null, revoked_at: null },
];

function installFetch(authenticated = true) {
  return vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = new URL(String(input), "http://localhost");
    if (url.pathname === "/api/v1/users/me") return Response.json(authenticated ? user : { detail: "Not authenticated" }, { status: authenticated ? 200 : 401 });
    if (url.pathname === "/api/v1/account/usage") return Response.json(usage);
    if (url.pathname === "/api/v1/api-keys" && init?.method === "POST") return Response.json({ ...keys[0], id: "new", name: "CI runner", secret: "dsb_live_only_once_123456", prefix: "dsb_live_only_o", last_four: "3456" }, { status: 201 });
    if (url.pathname === "/api/v1/api-keys") return Response.json(keys);
    if (url.pathname.startsWith("/api/v1/api-keys/") && init?.method === "DELETE") return new Response(null, { status: 204 });
    return Response.json({ detail: "Not found" }, { status: 404 });
  });
}

function renderAt(path: string) { return render(<MemoryRouter initialEntries={[path]}><App/></MemoryRouter>); }

beforeEach(() => { localStorage.clear(); localStorage.setItem("dashanbing-locale", "zh"); });
afterEach(() => vi.restoreAllMocks());

describe("API center", () => {
  test("publishes an accurate public task API guide in the dedicated shell", async () => {
    vi.stubGlobal("fetch", installFetch(false));
    renderAt("/api/docs");

    expect(await screen.findByRole("heading", { name: "大山冰 API 文档" })).toBeVisible();
    const nav = screen.getByRole("navigation", { name: "API 导航" });
    expect(within(nav).getByRole("link", { name: "API 文档" })).toHaveAttribute("href", "/api/docs");
    expect(within(nav).getByRole("link", { name: "API 管理" })).toHaveAttribute("href", "/api/keys");
    expect(screen.getByRole("navigation", { name: "本文目录" })).toBeVisible();
    expect(screen.getByText("Authorization: Bearer dsb_live_…", { exact: true })).toBeVisible();
    expect(screen.getByText("enrollment_video")).toBeVisible();
    expect(screen.getAllByText("cam_04")[0]).toBeVisible();
    expect(screen.getByText("draft → uploading → queued → running → completed", { exact: true })).toBeVisible();
    expect(screen.getAllByText(/\/api\/v1\/tasks/).length).toBeGreaterThan(5);
    expect(screen.getByText(/python3 -c/)).toBeVisible();
    expect(screen.getByText(/while :; do/)).toBeVisible();
    expect(screen.getByText("运行前执行：python3 -m pip install requests")).toBeVisible();
    expect([...document.querySelectorAll(".api-code")].some(block => block.textContent?.includes("failed|canceled|expired"))).toBe(true);
    expect(screen.queryByText(/\/api\/v1\/analyses/)).not.toBeInTheDocument();
    expect(screen.queryByText("客户端")).not.toBeInTheDocument();
    expect(screen.queryByText("生态")).not.toBeInTheDocument();
    expect(screen.queryByText("资讯")).not.toBeInTheDocument();
  });

  test("keeps the English guide executable and documents upload cancellation", async () => {
    localStorage.setItem("dashanbing-locale", "en");
    vi.stubGlobal("fetch", installFetch(false));
    renderAt("/api/docs");

    expect(await screen.findByRole("heading", { name: "DaShanBing API Docs" })).toBeVisible();
    expect(screen.getByText("Before running: python3 -m pip install requests")).toBeVisible();
    expect(screen.getByText(/multipart field/, { selector: "li" })).toBeVisible();
    expect(screen.getByText(/draft, uploading, queued, or running tasks/)).toBeVisible();
  });

  test("creates a key, reveals its full secret once, copies it, then closes without retaining it", async () => {
    const fetchMock = installFetch();
    vi.stubGlobal("fetch", fetchMock);
    const operator = userEvent.setup();
    const writeText = vi.spyOn(navigator.clipboard, "writeText").mockResolvedValue(undefined);
    renderAt("/api/keys");

    expect(await screen.findByRole("heading", { name: "API 管理" })).toBeVisible();
    expect(await screen.findByText("4 / 20")).toBeVisible();
    expect(screen.getByText("24 小时 · 7 天 · 30 天 · 180 天")).toBeVisible();
    expect(screen.getByText("dsb_live_abcd12••••9xyz")).toBeVisible();
    expect(screen.queryByRole("button", { name: /复制 Production/ })).not.toBeInTheDocument();
    await operator.click(screen.getByRole("button", { name: "创建 API 密钥" }));
    const createDialog = screen.getByRole("dialog", { name: "创建 API 密钥" });
    await operator.type(within(createDialog).getByLabelText("密钥名称"), "CI runner");
    await operator.click(within(createDialog).getByRole("button", { name: "创建密钥" }));

    const secretDialog = await screen.findByRole("dialog", { name: "保存新密钥" });
    expect((within(secretDialog).getByRole("textbox", { name: "新 API 密钥" }) as HTMLInputElement).value).toBe("dsb_live_only_once_123456");
    expect(within(secretDialog).getByRole("alert")).toHaveTextContent("只显示一次");
    await operator.click(within(secretDialog).getByRole("button", { name: "复制完整密钥" }));
    expect(writeText).toHaveBeenCalledWith("dsb_live_only_once_123456");
    expect(await within(secretDialog).findByText("已复制")).toBeVisible();
    await operator.click(within(secretDialog).getByRole("button", { name: "我已保存" }));
    expect(screen.queryByText("dsb_live_only_once_123456")).not.toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledWith("/api/v1/api-keys", expect.objectContaining({ method: "POST" }));
  });

  test("keeps a one-time secret keyboard-selectable after clipboard failure", async () => {
    vi.stubGlobal("fetch", installFetch());
    const operator = userEvent.setup();
    vi.spyOn(navigator.clipboard, "writeText").mockRejectedValue(new Error("denied"));
    renderAt("/api/keys");
    await operator.click(await screen.findByRole("button", { name: "创建 API 密钥" }));
    const createDialog = screen.getByRole("dialog", { name: "创建 API 密钥" });
    await operator.type(within(createDialog).getByLabelText("密钥名称"), "CI runner");
    await operator.click(within(createDialog).getByRole("button", { name: "创建密钥" }));

    const secretDialog = await screen.findByRole("dialog", { name: "保存新密钥" });
    await operator.click(within(secretDialog).getByRole("button", { name: "复制完整密钥" }));
    const fallback = within(secretDialog).getByRole("textbox", { name: "新 API 密钥" }) as HTMLInputElement;
    expect(fallback.value).toBe("dsb_live_only_once_123456");
    await waitFor(() => expect(fallback).toHaveFocus());
    expect(fallback.selectionStart).toBe(0);
    expect(fallback.selectionEnd).toBe(fallback.value.length);
  });

  test("keeps API-key creation failures announced inside the active dialog", async () => {
    vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const path = new URL(String(input), "http://localhost").pathname;
      if (path === "/api/v1/users/me") return Response.json(user);
      if (path === "/api/v1/account/usage") return Response.json(usage);
      if (path === "/api/v1/api-keys" && init?.method === "POST") return Response.json({ detail: "Key quota reached" }, { status: 429 });
      if (path === "/api/v1/api-keys") return Response.json(keys);
      return Response.json({ detail: "Not found" }, { status: 404 });
    }));
    const operator = userEvent.setup();
    renderAt("/api/keys");
    await operator.click(await screen.findByRole("button", { name: "创建 API 密钥" }));
    const dialog = screen.getByRole("dialog", { name: "创建 API 密钥" });
    await operator.type(within(dialog).getByLabelText("密钥名称"), "CI runner");
    await operator.click(within(dialog).getByRole("button", { name: "创建密钥" }));

    expect(await within(dialog).findByRole("alert")).toHaveTextContent("Key quota reached");
  });

  test("keeps a revoke failure announced inside its confirmation dialog", async () => {
    vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const path = new URL(String(input), "http://localhost").pathname;
      if (path === "/api/v1/users/me") return Response.json(user);
      if (path === "/api/v1/account/usage") return Response.json(usage);
      if (path === "/api/v1/api-keys") return Response.json(keys);
      if (path === "/api/v1/api-keys/active" && init?.method === "DELETE") return Response.json({ detail: "Already revoked" }, { status: 409 });
      return Response.json({ detail: "Not found" }, { status: 404 });
    }));
    const operator = userEvent.setup();
    renderAt("/api/keys");
    await operator.click(await screen.findByRole("button", { name: "撤销 Production" }));
    const dialog = screen.getByRole("dialog", { name: "撤销 API 密钥" });
    await operator.click(within(dialog).getByRole("button", { name: "确认撤销" }));

    expect(await within(dialog).findByRole("alert")).toHaveTextContent("Already revoked");
  });

  test("keeps a busy revoke dialog focusable and announces its pending state", async () => {
    let resolveDelete: (() => void) | undefined;
    vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const path = new URL(String(input), "http://localhost").pathname;
      if (path === "/api/v1/users/me") return Response.json(user);
      if (path === "/api/v1/account/usage") return Response.json(usage);
      if (path === "/api/v1/api-keys") return Response.json(keys);
      if (path === "/api/v1/api-keys/active" && init?.method === "DELETE") return new Promise<Response>(resolve => { resolveDelete = () => resolve(new Response(null, { status: 204 })); });
      return Response.json({ detail: "Not found" }, { status: 404 });
    }));
    const operator = userEvent.setup();
    renderAt("/api/keys");
    await operator.click(await screen.findByRole("button", { name: "撤销 Production" }));
    const dialog = screen.getByRole("dialog", { name: "撤销 API 密钥" });
    await operator.click(within(dialog).getByRole("button", { name: "确认撤销" }));

    expect(dialog).toHaveAttribute("aria-busy", "true");
    expect(within(dialog).getByRole("status")).toHaveTextContent("正在撤销");
    expect(within(dialog).getByRole("button", { name: "确认撤销" })).toBeDisabled();
    await operator.keyboard("{Tab}");
    expect(dialog).toHaveFocus();
    resolveDelete?.();
  });

  test("requires confirmation before revoking a key and refreshes list and usage", async () => {
    const fetchMock = installFetch();
    vi.stubGlobal("fetch", fetchMock);
    const operator = userEvent.setup();
    renderAt("/api/keys");
    await screen.findByText("Production");
    await operator.click(screen.getByRole("button", { name: "撤销 Production" }));
    const dialog = screen.getByRole("dialog", { name: "撤销 API 密钥" });
    await operator.click(within(dialog).getByRole("button", { name: "确认撤销" }));
    await waitFor(() => expect(fetchMock).toHaveBeenCalledWith("/api/v1/api-keys/active", expect.objectContaining({ method: "DELETE" })));
    expect(await screen.findByRole("status")).toHaveTextContent("密钥已撤销");
  });

  test("restores the invoking control after closing API-key dialogs", async () => {
    vi.stubGlobal("fetch", installFetch());
    const operator = userEvent.setup();
    renderAt("/api/keys");

    const trigger = await screen.findByRole("button", { name: "创建 API 密钥" });
    await operator.click(trigger);
    expect(screen.getByRole("dialog", { name: "创建 API 密钥" })).toBeVisible();
    await operator.keyboard("{Escape}");
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    await waitFor(() => expect(trigger).toHaveFocus());
  });

  test("expires the browser session when API management receives a 401", async () => {
    let authenticated = true;
    vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL) => {
      const path = new URL(String(input), "http://localhost").pathname;
      if (path === "/api/v1/users/me") return Response.json(authenticated ? user : { detail: "Not authenticated" }, { status: authenticated ? 200 : 401 });
      if (path === "/api/v1/api-keys") { authenticated = false; return Response.json({ detail: "Not authenticated" }, { status: 401 }); }
      return Response.json(usage);
    }));
    renderAt("/api/keys");

    expect(await screen.findByRole("heading", { name: "登录大山冰" })).toBeVisible();
  });
});
