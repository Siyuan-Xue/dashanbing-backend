import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, useLocation } from "react-router-dom";
import { beforeEach, describe, expect, test, vi } from "vitest";

import App from "./App";

const anonymousResponse = () =>
  new Response(JSON.stringify({ detail: "Not authenticated" }), {
    status: 401,
    headers: { "Content-Type": "application/json" },
  });

function LocationProbe() {
  const location = useLocation();
  return <output data-testid="location">{location.pathname}{location.search}</output>;
}

function renderAt(path = "/") {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <App />
      <LocationProbe />
    </MemoryRouter>,
  );
}

describe("public foundation", () => {
  beforeEach(() => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(anonymousResponse()));
  });

  test("renders the scoped public header and full public landing story", async () => {
    renderAt();

    expect(await screen.findByRole("heading", { name: "让多路训练视频，变成可复盘的篮球洞察" })).toBeVisible();
    expect(screen.getByText(/离开页面|稍后回来/)).toBeVisible();

    const navigation = screen.getByRole("navigation", { name: "主导航" });
    expect(within(navigation).getAllByRole("link")).toHaveLength(2);
    expect(within(navigation).getByRole("link", { name: "首页" })).toHaveAttribute("href", "/");
    expect(within(navigation).getByRole("link", { name: "API" })).toHaveAttribute("href", "/api/docs");

    expect(screen.getByRole("link", { name: "GitHub" })).toHaveAttribute(
      "href",
      "https://github.com/Siyuan-Xue/dashanbing-backend",
    );
    expect(screen.getByRole("link", { name: "在线使用" })).toHaveAttribute("href", "/workspace/new");
    expect(screen.getByRole("link", { name: "登录" })).toHaveAttribute("href", "/login");
    expect(screen.getByLabelText("大山冰标志")).toBeVisible();

    expect(screen.getAllByTestId("capability-card")).toHaveLength(3);
    expect(screen.getAllByTestId("public-example-card")).toHaveLength(2);
    expect(screen.getByRole("heading", { name: "快速演示" })).toBeVisible();
    expect(screen.getByRole("heading", { name: "混合动作" })).toBeVisible();

    expect(screen.queryByText(/客户端|合集|生态|资讯|促销/)).not.toBeInTheDocument();
  });

  test("honors system dark mode once and persists a user theme choice", async () => {
    vi.mocked(matchMedia).mockImplementation((query: string) => ({
      matches: query === "(prefers-color-scheme: dark)",
      media: query,
      onchange: null,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      addListener: vi.fn(),
      removeListener: vi.fn(),
      dispatchEvent: vi.fn(),
    }));
    const user = userEvent.setup();
    const first = renderAt();

    await waitFor(() => expect(document.documentElement).toHaveAttribute("data-theme", "dark"));
    await user.click(screen.getByRole("button", { name: "切换到浅色主题" }));
    expect(document.documentElement).toHaveAttribute("data-theme", "light");
    expect(localStorage.getItem("dashanbing-theme")).toBe("light");

    first.unmount();
    renderAt();
    await waitFor(() => expect(document.documentElement).toHaveAttribute("data-theme", "light"));
  });

  test("switches locale and restores it on the next render", async () => {
    const user = userEvent.setup();
    const first = renderAt();

    await user.click(await screen.findByRole("button", { name: "English" }));
    expect(screen.getByRole("heading", { name: "Turn multi-angle training video into basketball insight you can review" })).toBeVisible();
    expect(document.documentElement.lang).toBe("en");
    expect(localStorage.getItem("dashanbing-locale")).toBe("en");

    first.unmount();
    renderAt();
    expect(await screen.findByRole("link", { name: "Home" })).toBeVisible();
  });
});

describe("authentication and protected routes", () => {
  test("guards every planned private route and keeps the full redirect target", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(anonymousResponse()));
    renderAt("/workspace/tasks?status=running");

    await waitFor(() => {
      expect(screen.getByTestId("location")).toHaveTextContent(
        "/login?next=%2Fworkspace%2Ftasks%3Fstatus%3Drunning",
      );
    });
    expect(screen.getByRole("heading", { name: "登录大山冰" })).toBeVisible();
  });

  test("logs in with username or email, refreshes cookie auth, and redirects back", async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url.endsWith("/api/v1/users/me")) {
        if (fetchMock.mock.calls.filter(([value]) => String(value).endsWith("/api/v1/users/me")).length === 1) {
          return anonymousResponse();
        }
        return Response.json({ id: 7, username: "coach", email: "coach@example.com", is_active: true });
      }
      if (url.endsWith("/api/v1/login/access-token")) {
        expect(init?.credentials).toBe("include");
        expect(init?.body).toBeInstanceOf(URLSearchParams);
        expect(String(init?.body)).toBe("username=coach%40example.com&password=practice123");
        return Response.json({ access_token: "cookie-backed", token_type: "bearer" });
      }
      return anonymousResponse();
    });
    vi.stubGlobal("fetch", fetchMock);
    const user = userEvent.setup();
    renderAt("/login?next=%2Fworkspace%2Ftasks");

    await user.type(screen.getByLabelText("用户名或邮箱"), "coach@example.com");
    await user.type(screen.getByLabelText("密码"), "practice123");
    await user.click(screen.getByRole("button", { name: "登录" }));

    await waitFor(() => expect(screen.getByTestId("location")).toHaveTextContent("/workspace/tasks"));
    expect(await screen.findByText("coach")).toBeVisible();
  });

  test("validates registration locally and surfaces a backend conflict", async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      if (String(input).endsWith("/api/v1/register")) {
        return new Response(JSON.stringify({ detail: "Username or email is already registered" }), {
          status: 409,
          headers: { "Content-Type": "application/json" },
        });
      }
      return anonymousResponse();
    });
    vi.stubGlobal("fetch", fetchMock);
    const user = userEvent.setup();
    renderAt("/register");

    await user.type(await screen.findByLabelText("用户名"), "ab");
    await user.type(screen.getByLabelText("邮箱"), "not-an-email");
    await user.type(screen.getByLabelText("密码"), "short");
    await user.click(screen.getByRole("button", { name: "创建账号" }));
    expect(screen.getByText("用户名至少需要 3 个字符")).toBeVisible();
    expect(fetchMock).not.toHaveBeenCalledWith("/api/v1/register", expect.anything());

    await user.clear(screen.getByLabelText("用户名"));
    await user.type(screen.getByLabelText("用户名"), "coach");
    await user.clear(screen.getByLabelText("邮箱"));
    await user.type(screen.getByLabelText("邮箱"), "coach@example.com");
    await user.clear(screen.getByLabelText("密码"));
    await user.type(screen.getByLabelText("密码"), "practice123");
    await user.click(screen.getByRole("button", { name: "创建账号" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("该用户名或邮箱已被注册");
  });
});
