import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, useLocation } from "react-router-dom";
import { beforeEach, expect, test, vi } from "vitest";
import App from "../App";

const account = (role: string) => ({ id: 7, username: "operator", email: "operator@example.test", is_active: true, role });
function Probe() { const location = useLocation(); return <output data-testid="location">{location.pathname}</output>; }
function view(path: string) { render(<MemoryRouter initialEntries={[path]}><App/><Probe/></MemoryRouter>); }
function serve(role: string | null) {
  const requests: string[] = [];
  let session = role;
  vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const path = new URL(String(input), "http://localhost").pathname;
    requests.push(path);
    if (path === "/api/v1/users/me") return session ? Response.json(account(session)) : Response.json({ detail: "Unauthorized" }, { status: 401 });
    if (path === "/api/v1/login/access-token") { session = "admin"; return Response.json({ access_token: "test", token_type: "bearer" }); }
    if (path === "/api/v1/logout" && init?.method === "POST") { session = null; return new Response(null, { status: 204 }); }
    if (path === "/api/v1/tasks") return Response.json({ items: [], total: 0, page: 1, page_size: 20 });
    return Response.json({ detail: "Unavailable" }, { status: 503 });
  }));
  return requests;
}
beforeEach(() => localStorage.setItem("dashanbing-locale", "en"));

test("admin entering the workspace lands in admin without loading user tasks", async () => {
  const requests = serve("admin"); view("/workspace/tasks");
  await waitFor(() => expect(screen.getByTestId("location")).toHaveTextContent(/^\/admin\/overview$/));
  expect(screen.getByRole("navigation", { name: "Administrator navigation" })).toBeVisible();
  expect(screen.getByRole("link", { name: "Overview" })).toHaveAttribute("aria-current", "page");
  expect(requests).not.toContain("/api/v1/tasks");
  expect(screen.queryByRole("link", { name: "Create task" })).not.toBeInTheDocument();
});
test("ordinary account is forbidden from admin and keeps its workspace link", async () => {
  const requests = serve("user"); view("/admin/users");
  expect(await screen.findByRole("heading", { name: "Administrator access required" })).toBeVisible();
  expect(screen.getByRole("link", { name: "Back to workspace" })).toHaveAttribute("href", "/workspace/new");
  expect(requests.some(path => path.startsWith("/api/v1/admin/"))).toBe(false);
});
test("admin login ignores an ordinary next destination", async () => {
  serve(null); const user = userEvent.setup(); view("/login?next=%2Fworkspace%2Ftasks");
  await user.type(await screen.findByLabelText("Username or email"), "operator");
  await user.type(screen.getByLabelText("Password"), "password123");
  await user.click(screen.getByRole("button", { name: "Log in" }));
  expect(await screen.findByRole("navigation", { name: "Administrator navigation" })).toBeVisible();
  expect(screen.getByTestId("location")).toHaveTextContent(/^\/admin(?:\/overview)?$/);
});
test("admin header account exposes only its role destination and logout works", async () => {
  serve("admin"); const user = userEvent.setup(); view("/");
  await user.click(await screen.findByRole("button", { name: /Account.*operator/ }));
  const menu = screen.getByRole("region", { name: "Account" });
  expect(within(menu).getByRole("link", { name: "Administration" })).toHaveAttribute("href", "/admin");
  expect(within(menu).queryByRole("link", { name: /workspace/i })).not.toBeInTheDocument();
  await user.click(within(menu).getByRole("button", { name: "Log out" }));
  expect(await screen.findByRole("link", { name: "Log in" })).toBeVisible();
});
test("ordinary task route remains available", async () => {
  serve("user"); view("/workspace/tasks");
  expect(await screen.findByRole("heading", { name: "No tasks yet" })).toBeVisible();
  expect(screen.getByTestId("location")).toHaveTextContent("/workspace/tasks");
});

test("admin sidebar exposes theme, language and logout directly beside the account", async () => {
  const requests = serve("admin"); const user = userEvent.setup(); view("/admin/overview");
  const avatar = await screen.findByRole("button", { name: /Account.*operator/ });
  expect(screen.queryByRole("region", { name: "Account" })).not.toBeInTheDocument();
  expect(screen.queryByText("Recent tasks")).not.toBeInTheDocument();
  expect(within(avatar).getByText("operator")).toBeVisible();
  expect(screen.getByRole("button", { name: "Log out" })).toBeVisible();
  const themeButton = screen.getByRole("button", { name: /dark theme/i });
  await user.click(themeButton);
  expect(document.documentElement.dataset.theme).toBe("dark");
  await user.click(screen.getByRole("button", { name: /light theme/i }));
  await user.click(screen.getByRole("button", { name: "中文" }));
  expect(screen.getByRole("button", { name: "退出登录" })).toBeVisible();
  await user.click(screen.getByRole("button", { name: "English" }));
  await user.click(avatar);
  const menu = screen.getByRole("region", { name: "Account" });
  expect(within(menu).getByText("Administrator")).toBeVisible();
  expect(within(menu).getByText("operator@example.test")).toBeVisible();
  await user.keyboard("{Escape}");
  expect(avatar).toHaveFocus();
  expect(screen.queryByRole("region", { name: "Account" })).not.toBeInTheDocument();
  await user.click(screen.getByRole("button", { name: "Log out" }));
  expect(await screen.findByRole("link", { name: "Log in" })).toBeVisible();
  expect(requests).not.toContain("/api/v1/tasks");
});

test("admin mobile navigation traps focus, switches sections and supports logout", async () => {
  vi.mocked(window.matchMedia).mockImplementation(query => ({ matches: query === "(max-width: 767px)", media: query, addEventListener: vi.fn(), removeEventListener: vi.fn() } as unknown as MediaQueryList));
  serve("admin"); const user = userEvent.setup(); view("/admin");
  const trigger = await screen.findByRole("button", { name: "Open administrator menu" });
  await user.click(trigger);
  const drawer = screen.getByRole("dialog", { name: "Administrator navigation" });
  expect(within(within(drawer).getByRole("navigation")).getAllByRole("link").map(link => link.getAttribute("href"))).toEqual([ "/admin/overview", "/admin/users", "/admin/scheduling", "/admin/quotas", "/admin/operations", "/admin/audit"]);
  within(drawer).getByRole("link", { name: "DaShanBing home" }).focus();
  await user.keyboard("{Shift>}{Tab}{/Shift}");
  expect(within(drawer).getByRole("button", { name: "Log out" })).toHaveFocus();
  await user.click(within(drawer).getByRole("link", { name: "Audit log" }));
  expect(await screen.findByRole("heading", { name: "Audit log" })).toBeVisible();
  expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  await user.click(trigger);
  await user.click(screen.getByRole("button", { name: /Account.*operator/ }));
  await user.click(screen.getByRole("button", { name: "Log out" }));
  expect(await screen.findByRole("link", { name: "Log in" })).toBeVisible();
});
