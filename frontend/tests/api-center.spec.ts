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
  if (testInfo.project.name === "desktop-chromium") {
    await expect(page.getByRole("navigation", { name: "主导航" }).getByRole("link")).toHaveCount(2);
  }
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
    await page.getByRole("button", { name: "关闭 API 导航" }).click();
    await page.getByRole("button", { name: "本文目录" }).click();
    await expect(page.getByRole("navigation", { name: "本文目录" })).toBeVisible();
  } else {
    await expect(page.getByRole("navigation", { name: "本文目录" })).toBeVisible();
    await expect(page.locator(".api-toc")).toHaveCSS("position", "sticky");
  }
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
});

test("API management never offers a fake copy action and reveals create secret once", async ({ page, context, baseURL }) => {
  await context.grantPermissions(["clipboard-write"], { origin: new URL(baseURL!).origin });
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

test("defers fifth-key secret dismissal focus until delayed refresh settles", async ({ page }, testInfo) => {
  test.skip(testInfo.project.name !== "desktop-chromium", "Controlled Chromium focus coverage.");
  let active = 4;
  let keyReads = 0;
  await page.route("**/api/v1/**", async route => {
    const { pathname } = new URL(route.request().url());
    if (pathname === "/api/v1/users/me") return route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(user) });
    if (pathname === "/api/v1/account/usage") return route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ ...usage, active_api_keys: { used: active, limit: 5 } }) });
    if (pathname === "/api/v1/api-keys" && route.request().method() === "POST") { active = 5; return route.fulfill({ status: 201, contentType: "application/json", body: JSON.stringify({ ...key, id: "fifth", secret: "dsb_live_fifth_once" }) }); }
    if (pathname === "/api/v1/api-keys") {
      if (++keyReads > 1) await new Promise(resolve => setTimeout(resolve, 900));
      return route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(Array.from({ length: active }, (_, index) => ({ ...key, id: `key-${index}`, last_four: `00${index}` }))) });
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
  expect(await page.evaluate(() => document.activeElement === document.body)).toBe(false);
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

test("mobile API navigation expands inline and leaves keyboard focus free to reach the article", async ({ page }, testInfo) => {
  test.skip(testInfo.project.name !== "mobile-chromium", "Inline navigation is phone-only.");
  await page.goto("/api/docs");
  const contentTop = await page.locator(".api-docs-layout").evaluate(node => node.getBoundingClientRect().top);
  await page.getByRole("button", { name: "打开 API 导航" }).click();
  const nav = page.getByRole("navigation", { name: "API 导航", exact: true });
  expect(await page.locator(".api-docs-layout").evaluate(node => node.getBoundingClientRect().top)).toBeGreaterThan(contentTop);
  await page.keyboard.press("Tab");
  await expect(nav.getByRole("link", { name: "API 文档" })).toBeFocused();
  await page.keyboard.press("Tab");
  await expect(nav.getByRole("link", { name: "API 管理" })).toBeFocused();
  await page.keyboard.press("Tab");
  await expect(page.getByRole("button", { name: "本文目录" })).toBeFocused();
  await nav.getByRole("link", { name: "API 文档" }).focus();
  await page.keyboard.press("Escape");
  await expect(page.getByRole("button", { name: "打开 API 导航" })).toBeFocused();
  await expect(nav).toBeHidden();
});

test("child hash links survive reload, back and forward with headings below the public header", async ({ page }) => {
  await page.goto("/api/docs#upload");
  const assertTarget = async (id: string) => {
    await expect(page).toHaveURL(new RegExp(`#${id}$`));
    const heading = page.locator(`.api-docs #${id}`);
    await expect(heading).toBeInViewport();
    await expect.poll(() => heading.evaluate(node => node.getBoundingClientRect().top)).toBeGreaterThanOrEqual(76);
  };
  await assertTarget("upload");
  await expect(page.locator('.api-toc [aria-current="location"]')).toHaveAttribute("href", "/api/docs#upload");
  const toggle = page.getByRole("button", { name: "本文目录" });
  if (await toggle.isVisible()) await toggle.click();
  const toc = page.getByRole("navigation", { name: "本文目录" });
  await toc.getByRole("link", { name: "Python", exact: true }).click();
  await assertTarget("python");
  await page.goBack();
  await assertTarget("upload");
  await page.goForward();
  await assertTarget("python");
  await page.reload();
  await assertTarget("python");
});

test("scrolling selects nested headings without rewriting history and keeps the TOC selection visible", async ({ page }, testInfo) => {
  test.skip(testInfo.project.name !== "desktop-chromium", "Desktop scroll tracking and short-window TOC.");
  await page.setViewportSize({ width: 1440, height: 400 });
  await page.goto("/api/docs#overview");
  await page.locator("#python").evaluate(node => window.scrollTo({ top: window.scrollY + node.getBoundingClientRect().top - 97, behavior: "instant" }));
  const selected = page.getByRole("navigation", { name: "本文目录" }).getByRole("link", { name: "Python", exact: true });
  await expect(selected).toHaveAttribute("aria-current", "location");
  await expect(selected).toBeInViewport();
  await expect(page).toHaveURL(/#overview$/);
  const bounds = await selected.evaluate(node => ({ link: node.getBoundingClientRect().toJSON(), toc: node.closest("nav")!.getBoundingClientRect().toJSON() }));
  expect(bounds.link.top).toBeGreaterThanOrEqual(bounds.toc.top);
  expect(bounds.link.bottom).toBeLessThanOrEqual(bounds.toc.bottom);
});

test("locale changes preserve the top of the docs page and its introduction", async ({ page }) => {
  await page.goto("/api/docs");
  expect(await page.evaluate(() => window.scrollY)).toBe(0);
  await page.getByRole("button", { name: "English", exact: true }).click();
  await expect(page.getByRole("button", { name: "中文", exact: true })).toBeFocused();
  await expect.poll(() => page.evaluate(() => window.scrollY)).toBe(0);
  await expect(page.locator(".api-page-header p")).toBeInViewport();
});

test("locale changes keep focus and align the current chapter instead of the stale hash", async ({ page }) => {
  await page.emulateMedia({ reducedMotion: "reduce" });
  await page.goto("/api/docs#overview");
  await expect(page.locator("#overview")).toBeFocused();
  await page.locator("#python").evaluate(node => {
    const offset = document.querySelector(".public-header")!.getBoundingClientRect().height + 21;
    window.scrollTo({ top: window.scrollY + node.getBoundingClientRect().top - offset, behavior: "instant" });
  });
  const selected = page.locator('.api-toc [aria-current="location"]');
  await expect(selected).toHaveAttribute("href", "/api/docs#python");
  await expect(page).toHaveURL(/#overview$/);
  // The header is already visible. Locator.click() auto-scrolls this sticky mobile
  // control before pointerdown, changing the chapter this test intends to preserve.
  const languageToggle = page.getByRole("button", { name: "English", exact: true });
  await expect(languageToggle).toBeInViewport();
  const bounds = (await languageToggle.boundingBox())!;
  await page.mouse.click(bounds.x + bounds.width / 2, bounds.y + bounds.height / 2);
  const language = page.getByRole("button", { name: "中文", exact: true });
  await expect(language).toBeFocused();
  await expect(selected).toHaveAttribute("href", "/api/docs#python");
  await expect(page).toHaveURL(/#overview$/);
  await expect.poll(() => page.locator("#python").evaluate(node => Math.abs(
    node.getBoundingClientRect().top - document.querySelector(".public-header")!.getBoundingClientRect().height - 21,
  ))).toBeLessThan(2);
});

test("API dialogs preserve expiry focus and prevent background scrolling until dismissal", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 500 });
  await page.goto("/api/keys");
  const trigger = page.getByRole("button", { name: "创建 API 密钥", exact: true });
  await trigger.click();
  const dialog = page.getByRole("dialog", { name: "创建 API 密钥" });
  await expect(dialog.getByLabel("密钥名称")).toBeFocused();
  const expiry = dialog.getByLabel("有效期");
  await expiry.focus();
  await expiry.selectOption("30");
  await expect(expiry).toBeFocused();
  await expect(page.locator("body")).toHaveCSS("overflow", "hidden");
  const scrollY = await page.evaluate(() => window.scrollY);
  await page.mouse.move(5, 250);
  await page.mouse.wheel(0, 300);
  await page.evaluate(() => new Promise<void>(resolve => requestAnimationFrame(() => requestAnimationFrame(() => resolve()))));
  expect(await page.evaluate(() => window.scrollY)).toBe(scrollY);
  await page.keyboard.press("Escape");
  await expect(dialog).toHaveCount(0);
  await expect(trigger).toBeFocused();
  await expect(page.locator("body")).not.toHaveCSS("overflow", "hidden");
});

for (const width of [320, 768, 1024, 1279, 1280, 1920]) {
  test(`API layout contains content and uses the correct TOC at ${width}px`, async ({ page }, testInfo) => {
    test.skip(testInfo.project.name !== "desktop-chromium", "One browser is sufficient for explicit viewport checks.");
    await page.setViewportSize({ width, height: 900 });
    await page.goto("/api/docs");
    const toggle = page.getByRole("button", { name: "本文目录" });
    if (width < 1280) {
      await expect(toggle).toBeVisible();
      await toggle.click();
    } else {
      await expect(toggle).toHaveCount(0);
      await expect(page.locator(".api-toc")).toHaveCSS("width", "196px");
    }
    await expect(page.getByRole("navigation", { name: "本文目录" })).toBeVisible();
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    await page.screenshot({ path: testInfo.outputPath(`docs-${width}.png`) });
    await page.goto("/api/keys");
    await expect(page.getByRole("heading", { name: "API 管理" })).toBeVisible();
    await expect(page.locator(".api-quota-grid article")).toHaveCount(4);
    await expect(page.locator(".api-toc")).toHaveCount(0);
    const mainRight = await page.locator("main").evaluate(node => node.getBoundingClientRect().right);
    expect(mainRight).toBe(width);
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    await page.screenshot({ path: testInfo.outputPath(`keys-${width}.png`) });
  });
}

for (const width of [390, 1440]) {
  test(`English dark API navigation and empty-key creation remain usable at ${width}px`, async ({ page }, testInfo) => {
    test.skip(testInfo.project.name !== "desktop-chromium", "Explicit viewport and theme coverage.");
    await page.setViewportSize({ width, height: 900 });
    await page.emulateMedia({ reducedMotion: "reduce" });
    await page.addInitScript(() => {
      localStorage.setItem("dashanbing-locale", "en");
      localStorage.setItem("dashanbing-theme", "dark");
    });
    await page.goto("/api/docs#result");
    await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");
    await expect(page.getByRole("heading", { name: "Get results", exact: true })).toBeInViewport();
    await expect(page.locator('.api-toc [aria-current="location"]')).toHaveAttribute("href", "/api/docs#result");
    await page.screenshot({ path: testInfo.outputPath(`docs-dark-en-${width}.png`) });
    await page.route("**/api/v1/api-keys", route => route.fulfill({ status: 200, contentType: "application/json", body: "[]" }));
    await page.route("**/api/v1/account/usage", route => route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ ...usage, active_api_keys: { used: 0, limit: 5 } }) }));
    await page.goto("/api/keys");
    await expect(page.getByText("No API keys yet. Create a key to start your server integration.")).toBeVisible();
    await page.screenshot({ path: testInfo.outputPath(`keys-empty-dark-en-${width}.png`) });
    await page.getByRole("button", { name: "Create API key", exact: true }).click();
    const dialog = page.getByRole("dialog", { name: "Create API key" });
    await expect(dialog.getByLabel("Key name")).toBeFocused();
    await expect(dialog.getByLabel("Expires in")).toHaveValue("90");
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    await page.screenshot({ path: testInfo.outputPath(`modal-dark-en-${width}.png`) });
    await page.keyboard.press("Escape");
    await expect(page.getByRole("button", { name: "Create API key", exact: true })).toBeFocused();
  });
}
