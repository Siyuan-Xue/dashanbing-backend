import { expect, test, type Page } from "@playwright/test";

const user = { id: 7, username: "coach", email: "coach@example.com", is_active: true };

async function openMenu(page: Page) {
  const menu = page.getByRole("button", { name: /打开导航菜单|Open navigation menu/ });
  if (await menu.isVisible()) await menu.click();
}

test.beforeEach(async ({ page }) => {
  // Every test API request stays in the fixture boundary, including post-login task loads.
  await page.route("**/api/v1/**", route => {
    if (new URL(route.request().url()).pathname === "/api/v1/tasks") return route.fulfill({status:200,json:{items:[],total:0,page:1,page_size:10}});
    return route.fulfill({status:404,json:{detail:"No fixture for this request"}});
  });
  await page.route("**/api/v1/users/me", (route) => route.fulfill({
    status: 401,
    contentType: "application/json",
    body: JSON.stringify({ detail: "Not authenticated" }),
  }));
  await page.goto("/");
});

test("public home keeps the approved navigation and story", async ({ page }) => {
  await expect(page.getByRole("heading", { name: "让我看看你打球什么b样" })).toBeVisible();
  await openMenu(page);
  await expect(page.getByRole("navigation", { name: "主导航" }).getByRole("link")).toHaveCount(2);
  await expect(page.getByTestId("capability-card")).toHaveCount(3);
  await expect(page.getByTestId("public-example-card")).toHaveCount(2);
  await expect(page.getByRole("link", { name: "GitHub" })).toHaveAttribute("href", "https://github.com/Siyuan-Xue/dashanbing-backend");
  await expect(page.getByRole("link", { name: "在线使用" })).toBeVisible();
});

test("theme and locale choices survive real clicks and reloads", async ({ page }) => {
  await openMenu(page);
  await page.getByRole("button", { name: "切换到深色主题" }).click();
  await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");
  await page.reload();
  await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");

  await openMenu(page);
  await page.getByRole("button", { name: "English" }).click();
  await expect(page.getByRole("navigation", { name: "Main navigation" })).toBeVisible();
  await expect(page.getByRole("link", { name: "DaShanBing home" })).toBeVisible();
  await expect(page).toHaveTitle("DaShanBing · Multi-camera basketball review");
  await page.reload();
  await openMenu(page);
  await expect(page.getByRole("link", { name: "Home", exact: true })).toBeVisible();
  await expect(page.locator('meta[name="description"]')).toHaveAttribute(
    "content",
    "DaShanBing turns multi-camera basketball training video into reviewable action and shooting insight",
  );
});

test("public navigation changes routes without a document request", async ({ page }) => {
  await openMenu(page);
  await page.getByRole("link", { name: "登录" }).click();
  await expect(page).toHaveURL(/\/login$/);
  await expect(page.getByRole("heading", { name: "登录大山冰" })).toBeVisible();

  await page.getByRole("link", { name: "大山冰首页" }).click();
  await expect(page).toHaveURL(/\/$/);
  await expect(page.getByRole("heading", { name: "让我看看你打球什么b样" })).toBeVisible();
});

test("protected routing redirects back after a mocked cookie-auth login", async ({ page }) => {
  let authenticated = false;
  await page.unroute("**/api/v1/users/me");
  await page.route("**/api/v1/users/me", (route) => route.fulfill({
    status: authenticated ? 200 : 401,
    contentType: "application/json",
    body: JSON.stringify(authenticated ? user : { detail: "Not authenticated" }),
  }));
  await page.route("**/api/v1/login/access-token", async (route) => {
    expect(route.request().postData()).toBe("username=coach%40example.com&password=practice123");
    authenticated = true;
    await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ access_token: "cookie-backed", token_type: "bearer" }) });
  });

  await page.goto("/workspace/tasks?status=running");
  await expect(page).toHaveURL(/\/login\?next=%2Fworkspace%2Ftasks%3Fstatus%3Drunning$/);
  await page.getByLabel("用户名或邮箱").fill("coach@example.com");
  await page.getByLabel("密码").fill("practice123");
  await page.getByRole("button", { name: "登录" }).click();

  await expect(page).toHaveURL(/\/workspace\/tasks\?status=running$/);
  const menu = page.getByRole("button", { name: "打开工作台菜单" });
  if (await menu.isVisible()) await menu.click();
  await expect(page.getByRole("link", { name: /coach/ })).toBeVisible();
});

test("registration permits the backend's 50-code-point astral username maximum", async ({ page }) => {
  const username = "🏀".repeat(50);
  let submittedUsername = "";
  await page.route("**/api/v1/register", async (route) => {
    submittedUsername = (route.request().postDataJSON() as { username: string }).username;
    await route.fulfill({
      status: 409,
      contentType: "application/json",
      body: JSON.stringify({ detail: "Username or email is already registered" }),
    });
  });
  await page.goto("/register");

  const usernameInput = page.getByLabel("用户名");
  await expect(usernameInput).not.toHaveAttribute("maxlength");
  await usernameInput.click();
  await page.keyboard.insertText(username);
  await expect(usernameInput).toHaveValue(username);
  await page.getByLabel("邮箱").fill("coach@example.com");
  await page.getByLabel("密码").fill("practice123");
  await page.getByRole("button", { name: "创建账号" }).click();

  await expect(page.getByRole("alert")).toContainText("该用户名或邮箱已被注册");
  expect(submittedUsername).toBe(username);
});

test("mobile header actions remain usable without horizontal overflow", async ({ page }, testInfo) => {
  test.skip(testInfo.project.name !== "mobile-chromium", "mobile-only layout assertion");

  await openMenu(page);
  const actions = page.locator(".header-actions");
  await expect(actions.getByRole("button", { name: "切换到深色主题" })).toBeVisible();
  await expect(actions.getByRole("button", { name: "English" })).toBeVisible();
  await expect(actions.getByRole("link", { name: "GitHub" })).toBeVisible();
  await expect(actions.getByRole("link", { name: "在线使用" })).toBeVisible();
  await expect(actions.getByRole("link", { name: "登录" })).toBeVisible();
  await actions.getByRole("button", { name: "English" }).click();
  await expect(actions.getByRole("button", { name: "中文" })).toBeVisible();

  const dimensions = await page.evaluate(() => ({ viewport: window.innerWidth, page: document.documentElement.scrollWidth }));
  expect(dimensions.page).toBeLessThanOrEqual(dimensions.viewport);
  const box = await actions.boundingBox();
  expect(box).not.toBeNull();
  expect(box!.x + box!.width).toBeLessThanOrEqual(dimensions.viewport);
});

 test("mobile navigation closes on Escape and on route changes", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  const toggle = page.locator(".public-menu-toggle");
  await toggle.focus();
  await page.keyboard.press("Enter");
  await expect(toggle).toHaveAttribute("aria-expanded", "true");
  await expect(page.getByRole("link", {name:"首页",exact:true})).toBeFocused();
  await page.keyboard.press("Tab");
  await expect(page.getByRole("link", {name:"API",exact:true})).toBeFocused();
  await page.keyboard.press("Escape");
  await expect(toggle).toHaveAttribute("aria-expanded", "false");
  await expect(toggle).toBeFocused();
  await toggle.click();
  await page.getByRole("link", { name: "API", exact: true }).click();
  await expect(page).toHaveURL(/\/api\/docs$/);
  await expect(page.locator(".public-menu-toggle")).toHaveAttribute("aria-expanded", "false");
});
