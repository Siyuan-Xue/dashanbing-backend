import { expect, test } from "@playwright/test";

const user = { id: 7, username: "coach", email: "coach@example.com", is_active: true };
const usage = { submitted_today: { used: 4, limit: 20 }, unfinished_tasks: { used: 2, limit: 5 }, drafts: { used: 1, limit: 3 }, active_api_keys: { used: 1, limit: 5 }, retention: { drafts: "24 hours", enrollment_data: "7 days", raw_inputs: "30 days", results: "180 days" } };
const key = { id: "key-1", name: "Production", prefix: "dsb_live_abcd12", last_four: "9xyz", status: "active", created_at: "2026-09-01T10:00:00Z", expires_at: "2026-12-01T10:00:00Z", last_used_at: null, revoked_at: null };

test.beforeEach(async ({ page }) => {
  await page.route("**/api/v1/**", async route => {
    const { pathname } = new URL(route.request().url());
    if (pathname === "/api/v1/users/me") return route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(user) });
    if (pathname === "/api/v1/account/usage") return route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(usage) });
    if (pathname === "/api/v1/api-keys" && route.request().method() === "POST") return route.fulfill({ status: 201, contentType: "application/json", body: JSON.stringify({ ...key, id: "key-2", name: "CI", prefix: "dsb_live_once12", last_four: "7890", secret: "dsb_live_once_visible_7890" }) });
    if (pathname === "/api/v1/api-keys") return route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify([key]) });
    if (pathname === "/api/v1/api-keys/key-1" && route.request().method() === "DELETE") return route.fulfill({ status: 204 });
    return route.fulfill({ status: 404, contentType: "application/json", body: JSON.stringify({ detail: "Not found" }) });
  });
});

test("API docs keep the public header contract and responsive navigation", async ({ page }, testInfo) => {
  await page.goto("/api/docs");
  await expect(page.getByRole("heading", { name: "大山冰 API 文档" })).toBeVisible();
  await expect(page.getByRole("navigation", { name: "主导航" }).getByRole("link")).toHaveCount(2);
  await expect(page.getByText("Authorization: Bearer dsb_live_…", { exact: true })).toBeVisible();
  await expect(page.getByText("enrollment_video", { exact: true })).toBeVisible();
  await expect(page.getByText(/\/api\/v1\/analyses/)).toHaveCount(0);
  const bodyTextContrast = await page.evaluate(() => {
    const values = (value: string) => value.match(/[\d.]+/g)!.slice(0, 3).map(Number);
    const luminance = (value: string) => {
      const [r, g, b] = values(value).map(channel => channel / 255).map(channel => channel <= .04045 ? channel / 12.92 : ((channel + .055) / 1.055) ** 2.4);
      return .2126 * r + .7152 * g + .0722 * b;
    };
    const foreground = getComputedStyle(document.querySelector<HTMLElement>(".api-page-header p")!).color;
    const background = getComputedStyle(document.body).backgroundColor;
    const [lighter, darker] = [luminance(foreground), luminance(background)].sort((a, b) => b - a);
    return (lighter + .05) / (darker + .05);
  });
  expect(bodyTextContrast).toBeGreaterThanOrEqual(4.5);
  if (testInfo.project.name === "mobile-chromium") {
    await expect(page.getByRole("navigation", { name: "本文目录" })).toBeHidden();
    await expect(page.getByRole("navigation", { name: "API 导航", exact: true })).toBeHidden();
    await page.getByRole("button", { name: "打开 API 导航" }).click();
    await expect(page.getByRole("navigation", { name: "API 导航", exact: true })).toBeVisible();
    await page.getByRole("complementary", { name: "API 导航" }).getByRole("button", { name: "关闭 API 导航" }).click();
  } else {
    await expect(page.getByRole("navigation", { name: "本文目录" })).toBeVisible();
    await expect(page.locator(".api-toc")).toHaveCSS("position", "sticky");
  }
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
});

test("API management never offers a fake copy action and reveals create secret once", async ({ page, context }) => {
  await context.grantPermissions(["clipboard-write"], { origin: "http://127.0.0.1:5173" });
  await page.goto("/api/keys");
  await expect(page.getByRole("heading", { name: "API 管理" })).toBeVisible();
  const mutedContrast = await page.evaluate(() => {
    const luminance = (value: string) => {
      const channels = value.match(/[\d.]+/g)!.slice(0, 3).map(Number).map(channel => channel / 255).map(channel => channel <= .04045 ? channel / 12.92 : ((channel + .055) / 1.055) ** 2.4);
      return .2126 * channels[0] + .7152 * channels[1] + .0722 * channels[2];
    };
    const foreground = luminance(getComputedStyle(document.querySelector<HTMLElement>(".api-page-header p")!).color);
    const background = luminance(getComputedStyle(document.body).backgroundColor);
    const [lighter, darker] = [foreground, background].sort((a, b) => b - a);
    return (lighter + .05) / (darker + .05);
  });
  expect(mutedContrast).toBeGreaterThanOrEqual(4.5);
  await expect(page.getByText("dsb_live_abcd12••••9xyz")).toBeVisible();
  await expect(page.getByRole("button", { name: /复制 Production/ })).toHaveCount(0);
  await page.getByRole("button", { name: "创建 API 密钥" }).click();
  const create = page.getByRole("dialog", { name: "创建 API 密钥" });
  await expect(create).toBeVisible();
  await create.getByLabel("密钥名称").fill("CI");
  await create.getByRole("button", { name: "创建密钥" }).click();
  const reveal = page.getByRole("dialog", { name: "保存新密钥" });
  await expect(reveal.getByRole("textbox", { name: "新 API 密钥" })).toHaveValue("dsb_live_once_visible_7890");
  await reveal.getByRole("button", { name: "复制完整密钥" }).click();
  await expect(reveal.getByRole("status")).toHaveText("已复制");
  await reveal.getByRole("button", { name: "我已保存" }).click();
  await expect(page.getByText("dsb_live_once_visible_7890")).toHaveCount(0);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
});

test("restores focus to a live API-key target after state-changing success", async ({ page }, testInfo) => {
  test.skip(testInfo.project.name !== "desktop-chromium", "Controlled Chromium focus coverage.");
  let active = 4;
  let rows = Array.from({ length: 4 }, (_, index) => ({ ...key, id: `key-${index}`, name: `Key ${index}`, last_four: `00${index}` }));
  await page.route("**/api/v1/**", async route => {
    const { pathname } = new URL(route.request().url());
    if (pathname === "/api/v1/users/me") return route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(user) });
    if (pathname === "/api/v1/account/usage") return route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ ...usage, active_api_keys: { used: active, limit: 5 } }) });
    if (pathname === "/api/v1/api-keys" && route.request().method() === "POST") {
      active = 5;
      rows = [...rows, { ...key, id: "key-5", name: "Fifth", last_four: "0005" }];
      return route.fulfill({ status: 201, contentType: "application/json", body: JSON.stringify({ ...key, id: "key-5", name: "Fifth", secret: "dsb_live_fifth_once" }) });
    }
    if (pathname === "/api/v1/api-keys") return route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(rows) });
    if (pathname === "/api/v1/api-keys/key-0" && route.request().method() === "DELETE") {
      active = 3;
      rows = rows.map(item => item.id === "key-0" ? { ...item, status: "revoked" } : item);
      return route.fulfill({ status: 204 });
    }
    return route.fulfill({ status: 404, contentType: "application/json", body: JSON.stringify({ detail: "Not found" }) });
  });

  await page.goto("/api/keys");
  await page.getByRole("button", { name: "创建 API 密钥" }).click();
  const create = page.getByRole("dialog", { name: "创建 API 密钥" });
  await create.getByLabel("密钥名称").fill("Fifth");
  await create.getByRole("button", { name: "创建密钥" }).click();
  await page.getByRole("dialog", { name: "保存新密钥" }).getByRole("button", { name: "我已保存" }).click();
  await expect(page.getByRole("heading", { name: /API 密钥 \(5\/5\)/ })).toBeFocused();
  await expect(page.getByRole("button", { name: "创建 API 密钥" })).toBeDisabled();

  active = 1;
  rows = [{ ...key, id: "key-0", name: "Key 0" }];
  await page.reload();
  await page.getByRole("button", { name: "撤销 Key 0" }).click();
  await page.getByRole("dialog", { name: "撤销 API 密钥" }).getByRole("button", { name: "确认撤销" }).click();
  await expect(page.getByRole("button", { name: "创建 API 密钥" })).toBeFocused();
  await expect(page.getByRole("button", { name: "撤销 Key 0" })).toHaveCount(0);
});

test("mobile API-key cards retain table headers and expose visible field labels", async ({ page }, testInfo) => {
  test.skip(testInfo.project.name !== "mobile-chromium", "Card labels are the phone presentation.");
  await page.goto("/api/keys");
  await expect(page.getByRole("heading", { name: "API 管理" })).toBeVisible();
  const table = page.locator(".api-key-table");
  await expect(table.getByRole("columnheader", { name: "名称" })).toHaveCount(1);
  await expect(table.locator("thead")).not.toHaveCSS("display", "none");
  const nameCell = table.getByRole("cell").first();
  await expect(nameCell).toHaveAttribute("data-label", "名称");
  expect(await nameCell.evaluate(node => getComputedStyle(node, "::before").content)).toContain("名称");
});

test("the mobile API navigation keeps keyboard focus inside the open drawer", async ({ page }, testInfo) => {
  test.skip(testInfo.project.name !== "mobile-chromium", "Drawer focus containment is phone-only.");
  await page.goto("/api/docs");
  await page.getByRole("button", { name: "打开 API 导航" }).click();

  const drawer = page.getByRole("complementary", { name: "API 导航" });
  const close = drawer.getByRole("button", { name: "关闭 API 导航" });
  await expect(close).toBeFocused();
  await page.keyboard.press("Shift+Tab");
  await expect(drawer.getByRole("link", { name: "API 管理" })).toBeFocused();
  await page.keyboard.press("Tab");
  await expect(close).toBeFocused();
});
