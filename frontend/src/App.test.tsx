import { act } from "react";
import type { ReactNode } from "react";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, useLocation } from "react-router-dom";
import { beforeEach, describe, expect, test, vi } from "vitest";

import App from "./App";
import { ThemeProvider } from "./providers/ThemeProvider";
import "./styles.css";

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

function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((next) => { resolve = next; });
  return { promise, resolve };
}

function ThemeAtChildRender({ children }: { children?: ReactNode }) {
  return <output data-testid="theme-at-child-render">{document.documentElement.dataset.theme || "unset"}{children}</output>;
}

function contrastRatio(foreground: string, background: string) {
  const channel = (value: number) => {
    const normalized = value / 255;
    return normalized <= 0.04045 ? normalized / 12.92 : ((normalized + 0.055) / 1.055) ** 2.4;
  };
  const luminance = (hex: string) => {
    const value = hex.trim().replace("#", "");
    const [red, green, blue] = [0, 2, 4].map((offset) => channel(Number.parseInt(value.slice(offset, offset + 2), 16)));
    return 0.2126 * red + 0.7152 * green + 0.0722 * blue;
  };
  const lighter = Math.max(luminance(foreground), luminance(background));
  const darker = Math.min(luminance(foreground), luminance(background));
  return (lighter + 0.05) / (darker + 0.05);
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

  test("applies first-visit system theme before descendants render", () => {
    vi.mocked(matchMedia).mockImplementation((query: string) => ({
      matches: query === "(prefers-color-scheme: dark)", media: query, onchange: null,
      addEventListener: vi.fn(), removeEventListener: vi.fn(), addListener: vi.fn(), removeListener: vi.fn(), dispatchEvent: vi.fn(),
    }));

    render(<ThemeProvider><ThemeAtChildRender /></ThemeProvider>);

    expect(screen.getByTestId("theme-at-child-render")).toHaveTextContent("dark");
  });

  test("applies a persisted theme before descendants render", () => {
    localStorage.setItem("dashanbing-theme", "dark");

    render(<ThemeProvider><ThemeAtChildRender /></ThemeProvider>);

    expect(screen.getByTestId("theme-at-child-render")).toHaveTextContent("dark");
  });

  test("keeps primary action text AA-readable in both themes", async () => {
    const user = userEvent.setup();
    renderAt();
    await screen.findByRole("heading", { name: "让多路训练视频，变成可复盘的篮球洞察" });

    for (const theme of ["light", "dark"] as const) {
      if (document.documentElement.dataset.theme !== theme) {
        await user.click(screen.getByRole("button", { name: theme === "dark" ? "切换到深色主题" : "切换到浅色主题" }));
      }
      const styles = getComputedStyle(document.documentElement);
      const onBrand = styles.getPropertyValue("--on-brand");
      const brand = styles.getPropertyValue("--brand");
      const brandStrong = styles.getPropertyValue("--brand-strong");
      expect({ onBrand, brand, brandStrong }).toEqual({
        onBrand: expect.stringMatching(/^\s*#[0-9a-f]{6}\s*$/i),
        brand: expect.stringMatching(/^\s*#[0-9a-f]{6}\s*$/i),
        brandStrong: expect.stringMatching(/^\s*#[0-9a-f]{6}\s*$/i),
      });
      expect(contrastRatio(onBrand, brand)).toBeGreaterThanOrEqual(4.5);
      expect(contrastRatio(onBrand, brandStrong)).toBeGreaterThanOrEqual(4.5);
    }
  });

  test("switches locale and restores it on the next render", async () => {
    const user = userEvent.setup();
    const first = renderAt();

    await user.click(await screen.findByRole("button", { name: "English" }));
    expect(screen.getByRole("heading", { name: "Turn multi-angle training video into basketball insight you can review" })).toBeVisible();
    expect(screen.getByRole("navigation", { name: "Main navigation" })).toBeVisible();
    expect(screen.getByRole("link", { name: "DaShanBing home" })).toBeVisible();
    expect(screen.getByLabelText("DaShanBing logo")).toBeVisible();
    expect(screen.getByLabelText("Wednesday shooting session")).toBeVisible();
    expect(document.title).toBe("DaShanBing · Multi-camera basketball review");
    expect(document.querySelector('meta[name="description"]')).toHaveAttribute(
      "content",
      "DaShanBing turns multi-camera basketball training video into reviewable action and shooting insight.",
    );
    expect(document.documentElement.lang).toBe("en");
    expect(localStorage.getItem("dashanbing-locale")).toBe("en");

    first.unmount();
    renderAt();
    expect(await screen.findByRole("link", { name: "Home" })).toBeVisible();
    expect(screen.getByRole("navigation", { name: "Main navigation" })).toBeVisible();
    expect(document.title).toBe("DaShanBing · Multi-camera basketball review");
  });

  test("keeps the workspace preview decorative instead of exposing a dead action", async () => {
    renderAt();
    await screen.findByLabelText("周三投篮训练");
    expect(screen.queryByRole("button", { name: "播放复盘预览" })).not.toBeInTheDocument();
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

  test("announces authentication bootstrap while a protected route waits", () => {
    vi.stubGlobal("fetch", vi.fn(() => new Promise<Response>(() => {})));
    renderAt("/workspace/tasks");

    const loading = screen.getAllByRole("status").find((element) => element.classList.contains("route-loading"));
    expect(loading).toHaveTextContent("正在确认登录状态");
  });

  test.each([
    ["server failure", vi.fn().mockResolvedValue(new Response("upstream failed", { status: 500 }))],
    ["network failure", vi.fn().mockRejectedValue(new TypeError("Failed to fetch"))],
    ["malformed response", vi.fn().mockResolvedValue(Response.json({ id: "not-a-user" }))],
  ])("shows a localized retry instead of treating a %s as logged out", async (_label, fetchMock) => {
    vi.stubGlobal("fetch", fetchMock);
    const user = userEvent.setup();
    renderAt("/workspace/tasks?status=running");

    expect(await screen.findByRole("alert")).toHaveTextContent("暂时无法确认登录状态");
    expect(screen.getByTestId("location")).toHaveTextContent("/workspace/tasks?status=running");

    fetchMock.mockResolvedValueOnce(anonymousResponse());
    await user.click(screen.getByRole("button", { name: "重试" }));
    await waitFor(() => expect(screen.getByTestId("location")).toHaveTextContent("/login?next="));
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

  test("a stale bootstrap response cannot overwrite a completed login", async () => {
    const bootstrap = deferred<Response>();
    let meCalls = 0;
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.endsWith("/api/v1/users/me")) {
        meCalls += 1;
        if (meCalls === 1) return bootstrap.promise;
        return Response.json({ id: 7, username: "coach", email: "coach@example.com", is_active: true });
      }
      if (url.endsWith("/api/v1/login/access-token")) return Response.json({ access_token: "cookie-backed", token_type: "bearer" });
      return anonymousResponse();
    });
    vi.stubGlobal("fetch", fetchMock);
    const user = userEvent.setup();
    renderAt("/login?next=%2Fworkspace%2Ftasks");

    await user.type(screen.getByLabelText("用户名或邮箱"), "coach");
    await user.type(screen.getByLabelText("密码"), "practice123");
    await user.click(screen.getByRole("button", { name: "登录" }));
    await waitFor(() => expect(screen.getByTestId("location")).toHaveTextContent("/workspace/tasks"));
    expect(await screen.findByText("coach")).toBeVisible();

    await act(async () => {
      bootstrap.resolve(anonymousResponse());
      await bootstrap.promise;
    });
    expect(meCalls).toBe(2);
    expect(fetchMock).toHaveBeenCalledTimes(5);
    expect(fetchMock.mock.calls.filter(([input]) => String(input).endsWith("/api/v1/login/access-token"))).toHaveLength(1);
    expect(fetchMock.mock.calls.filter(([input]) => String(input).startsWith("/api/v1/tasks?"))).toHaveLength(2);
    expect(screen.getByTestId("location")).toHaveTextContent("/workspace/tasks");
    expect(screen.getByText("coach")).toBeVisible();
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

    expect(await screen.findByLabelText("用户名")).toHaveAttribute("required");
    expect(screen.getByLabelText("用户名")).not.toHaveAttribute("maxlength");
    expect(screen.getByLabelText("邮箱")).toHaveAttribute("required");
    expect(screen.getByLabelText("邮箱")).not.toHaveAttribute("maxlength");
    expect(screen.getByLabelText("密码")).toHaveAttribute("required");
    expect(screen.getByLabelText("密码")).not.toHaveAttribute("maxlength");

    await user.type(screen.getByLabelText("用户名"), "ab");
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

  test("shows localized required registration errors without calling the backend", async () => {
    const fetchMock = vi.fn().mockResolvedValue(anonymousResponse());
    vi.stubGlobal("fetch", fetchMock);
    const user = userEvent.setup();
    renderAt("/register");

    await user.click(await screen.findByRole("button", { name: "创建账号" }));

    expect(screen.getByText("请输入用户名")).toBeVisible();
    expect(screen.getByText("请输入邮箱")).toBeVisible();
    expect(screen.getByText("请输入密码")).toBeVisible();
    expect(fetchMock).not.toHaveBeenCalledWith("/api/v1/register", expect.anything());
  });

  test("maps backend registration field validation to localized field copy", async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      if (String(input).endsWith("/api/v1/register")) {
        return new Response(JSON.stringify({ detail: [{ loc: ["body", "username"], msg: "String should have at most 50 characters", type: "string_too_long" }] }), {
          status: 422,
          headers: { "Content-Type": "application/json" },
        });
      }
      return anonymousResponse();
    });
    vi.stubGlobal("fetch", fetchMock);
    const user = userEvent.setup();
    renderAt("/register");

    await user.type(await screen.findByLabelText("用户名"), "coach");
    await user.type(screen.getByLabelText("邮箱"), "coach@example.com");
    await user.type(screen.getByLabelText("密码"), "practice123");
    await user.click(screen.getByRole("button", { name: "创建账号" }));

    expect(await screen.findByText("用户名不能超过 50 个字符")).toBeVisible();
    expect(screen.queryByText("暂时无法完成请求，请稍后重试")).not.toBeInTheDocument();
  });

  test.each([
    ["zh", "用户名至少需要 3 个字符"],
    ["en", "Username must be at least 3 characters"],
  ])("maps a FastAPI string_too_short issue in %s", async (locale, expected) => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      if (String(input).endsWith("/api/v1/register")) {
        return new Response(JSON.stringify({ detail: [{ loc: ["body", "username"], msg: "String should have at least 3 characters", type: "string_too_short" }] }), {
          status: 422,
          headers: { "Content-Type": "application/json" },
        });
      }
      return anonymousResponse();
    });
    vi.stubGlobal("fetch", fetchMock);
    const user = userEvent.setup();
    renderAt("/register");
    if (locale === "en") await user.click(await screen.findByRole("button", { name: "English" }));

    await user.type(await screen.findByLabelText(locale === "en" ? "Username" : "用户名"), "coach");
    await user.type(screen.getByLabelText(locale === "en" ? "Email" : "邮箱"), "coach@example.com");
    await user.type(screen.getByLabelText(locale === "en" ? "Password" : "密码"), "practice123");
    await user.click(screen.getByRole("button", { name: locale === "en" ? "Create account" : "创建账号" }));

    expect(await screen.findByText(expected)).toBeVisible();
    expect(screen.queryByText(locale === "en" ? "Username cannot exceed 50 characters" : "用户名不能超过 50 个字符")).not.toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledWith("/api/v1/register", expect.objectContaining({ method: "POST" }));
  });

  test("counts Unicode registration minima like the backend", async () => {
    const fetchMock = vi.fn().mockResolvedValue(anonymousResponse());
    vi.stubGlobal("fetch", fetchMock);
    const user = userEvent.setup();
    renderAt("/register");

    await user.type(await screen.findByLabelText("用户名"), "🏀🏀");
    await user.type(screen.getByLabelText("邮箱"), "coach@example.com");
    await user.type(screen.getByLabelText("密码"), "practice123");
    await user.click(screen.getByRole("button", { name: "创建账号" }));

    expect(screen.getByText("用户名至少需要 3 个字符")).toBeVisible();
    expect(fetchMock).not.toHaveBeenCalledWith("/api/v1/register", expect.anything());
  });

  test("keeps a backend-valid 50-code-point astral username enterable", async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL, _init?: RequestInit) => {
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
    const username = "🏀".repeat(50);
    renderAt("/register");

    const usernameInput = await screen.findByLabelText("用户名");
    await user.type(usernameInput, username);
    expect(usernameInput).toHaveValue(username);
    await user.type(screen.getByLabelText("邮箱"), "coach@example.com");
    await user.type(screen.getByLabelText("密码"), "practice123");
    await user.click(screen.getByRole("button", { name: "创建账号" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("该用户名或邮箱已被注册");
    const registerCall = fetchMock.mock.calls.find(([input]) => String(input).endsWith("/api/v1/register"));
    expect(JSON.parse(String(registerCall?.[1]?.body))).toMatchObject({ username });
  });

  test("maps structured required, email, and maximum issues in English", async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      if (String(input).endsWith("/api/v1/register")) {
        return new Response(JSON.stringify({ detail: [
          { loc: ["body", "username"], msg: "Field required", type: "missing" },
          { loc: ["body", "email"], msg: "Value is not a valid email address", type: "value_error" },
          { loc: ["body", "password"], msg: "String should have at most 128 characters", type: "string_too_long" },
        ] }), { status: 422, headers: { "Content-Type": "application/json" } });
      }
      return anonymousResponse();
    });
    vi.stubGlobal("fetch", fetchMock);
    const user = userEvent.setup();
    renderAt("/register");
    await user.click(await screen.findByRole("button", { name: "English" }));
    await user.type(screen.getByLabelText("Username"), "coach");
    await user.type(screen.getByLabelText("Email"), "coach@example.com");
    await user.type(screen.getByLabelText("Password"), "practice123");
    await user.click(screen.getByRole("button", { name: "Create account" }));

    expect(await screen.findByText("Enter a username")).toBeVisible();
    expect(screen.getByText("Enter a valid email address")).toBeVisible();
    expect(screen.getByText("Password cannot exceed 128 characters")).toBeVisible();
  });
});
