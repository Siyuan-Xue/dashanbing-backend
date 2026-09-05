import { expect, test } from "@playwright/test";

const user = { id: 7, username: "coach", email: "coach@example.com", is_active: true };
const task = { id: "task-1", title: "Friday shooting session", mode: "quick", source_type: "upload", preset_id: null, status: "completed", progress: 100, stage_message: "Complete", error_code: null, error_message: null, submitted_at: "2026-09-05T01:05:00Z", created_via: "tasks_api", retry_count: 0, created_at: "2026-09-05T01:00:00Z", updated_at: "2026-09-05T02:00:00Z", started_at: "2026-09-05T01:06:00Z", completed_at: "2026-09-05T02:00:00Z", inputs: [] };
const presets = [
  { id: "quick-demo", title: "Quick demo", description: "4 jump shots", expected_minutes: 9.4 },
  { id: "mixed-actions", title: "Mixed actions", description: "Triple threat and jump shots", expected_minutes: 26.7 },
  { id: "verified-outcome", title: "Verified outcome", description: "Free throws with outcome truth", expected_minutes: 30.9 },
  { id: "layup-demo", title: "Layup demo", description: "6 layups", expected_minutes: 14.3 },
];
const result = { registered_participant_count: 2, action_counts: { triple_threat: 1, free_throw: 0, jump_shot: 4, layup: 1 }, unsupported_event_count: 2, shots: { attempts: 5, makes: 3, misses: 1, undetermined: 1, make_rate: 0.6, unlinked_outcomes: 1 }, events: [{ event_index: 1, action_type: "jump_shot", start_ms: 1000, end_ms: 2200, time_ms: 1800, result: "make" }], media: {}, warnings: ["2 个事件属于当前版本未支持的动作类型。", "1 个投篮结果无法可靠关联到最终动作片段。"], disclaimer: "AI 识别结果，仅供训练复盘。" };
const usage = { submitted_today: { used: 4, limit: 20 }, unfinished_tasks: { used: 2, limit: 5 }, drafts: { used: 1, limit: 3 }, active_api_keys: { used: 1, limit: 5 }, retention: { drafts: "24 hours", enrollment_data: "7 days", raw_inputs: "30 days", results: "180 days" } };
const keys = [{ id: "key-1", name: "Production", prefix: "dsb_live_abcd12", last_four: "9xyz", status: "active", created_at: "2026-09-01T10:00:00Z", expires_at: "2026-12-01T10:00:00Z", last_used_at: null, revoked_at: null }];

test.beforeEach(async ({ page }) => {
  page.on("pageerror", error => { throw error; });
  await page.route("**/api/v1/**", async route => {
    const url = new URL(route.request().url());
    if (url.pathname === "/api/v1/users/me") return route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(user) });
    if (url.pathname === "/api/v1/presets") return route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(presets) });
    if (url.pathname === "/api/v1/presets/quick-demo/result") return route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(result) });
    if (url.pathname === "/api/v1/tasks/task-1/result") return route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(result) });
    if (url.pathname === "/api/v1/tasks/task-1") return route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(task) });
    if (url.pathname === "/api/v1/tasks") return route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ items: [task], total: 1, page: 1, page_size: 10 }) });
    if (url.pathname === "/api/v1/account/usage") return route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(usage) });
    if (url.pathname === "/api/v1/api-keys") return route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(keys) });
    return route.fulfill({ status: 404, contentType: "application/json", body: JSON.stringify({ detail: "Not found" }) });
  });
});

const pages = [
  ["home", "/"], ["login", "/login"], ["register", "/register"],
  ["new", "/workspace/new"], ["list", "/workspace/tasks"], ["detail", "/workspace/tasks/task-1"],
  ["example", "/workspace/examples/quick-demo"], ["settings", "/workspace/settings"],
  ["docs", "/api/docs"], ["keys", "/api/keys"],
] as const;
const locales = ["zh", "en"] as const;
const themes = ["light", "dark"] as const;
const widths = [390, 768, 1024, 1440, 1920];
type PageName = typeof pages[number][0];

async function ready(page: import("@playwright/test").Page, name: PageName, locale: typeof locales[number]) {
  const zh = locale === "zh";
  const headings: Record<PageName, string> = {
    home: zh ? "让我看看你打球什么b样" : "Turn multi-angle training video into basketball insight you can review",
    login: zh ? "登录大山冰" : "Log in to DaShanBing",
    register: zh ? "创建大山冰账号" : "Create a DaShanBing account",
    new: zh ? "创建分析任务" : "Create analysis task", list: zh ? "任务列表" : "Tasks",
    detail: "Friday shooting session", example: zh ? "快速演示" : "Quick demo",
    settings: zh ? "设置" : "Settings", docs: zh ? "大山冰 API 文档" : "DaShanBing API Docs", keys: zh ? "API 管理" : "API Management",
  };
  await expect(page.getByRole("heading", { name: headings[name], exact: true })).toBeVisible();
  if (name === "new") await expect(page.getByTestId("preset-card").first()).toBeVisible();
  if (name === "list") await expect(page.locator(".task-table tbody .task-title-link")).toContainText("Friday shooting session");
  if (name === "detail" || name === "example") await expect(page.locator(".result-workspace")).toBeVisible();
  if (name === "keys") await expect(page.getByText("Production", {exact:true})).toBeVisible();
  if (name === "settings") await expect(page.locator(".quota-grid article")).toHaveCount(4);
  if (!["login", "register"].includes(name)) await expect(page.locator(".account-link, .workspace-account")).toHaveAttribute("aria-label", /coach/);
  await page.evaluate(async () => {
    await document.fonts.ready;
    await Promise.all(Array.from(document.images).filter(img => img.loading !== "lazy" || (img.getBoundingClientRect().top < innerHeight && img.getBoundingClientRect().bottom > 0)).map(img => img.decode()));
  });
}

async function setup(page: import("@playwright/test").Page, name: PageName, path: string, locale: typeof locales[number], theme: typeof themes[number], width: number, height = 900) {
  await page.setViewportSize({width, height});
  await page.addInitScript(({locale, theme}) => {
    localStorage.setItem("dashanbing-locale", locale);
    localStorage.setItem("dashanbing-theme", theme);
  }, {locale, theme});
  await page.emulateMedia({reducedMotion: "reduce", colorScheme: theme});
  if (name === "login" || name === "register") await page.route("**/api/v1/users/me", route => route.fulfill({status:401, json:{detail:"Not authenticated"}}));
  await page.goto(path);
  await ready(page, name, locale);
}

for (const [name, path] of pages) for (const locale of locales) for (const theme of themes) for (const width of widths) {
  test(`visual ${name} ${width} ${locale} ${theme}`, async ({page}) => {
    await setup(page, name, path, locale, theme, width);
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    await expect(page).toHaveScreenshot(`${name}-${width}-${locale}-${theme}.png`, {animations:"disabled", maxDiffPixelRatio:0.001});
  });
}

// Boundary and short-window checks supplement the full language/theme matrix.
for (const [name, path] of pages) for (const [width, height] of [[320,700],[767,800],[769,800],[1279,800],[1281,800],[1440,480],[1024,320]]) {
  test(`boundary ${name} ${width}x${height}`, async ({page}, info) => {
    await setup(page, name, path, "en", "dark", width, height);
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    const sidebarFooter = page.locator(".workspace-sidebar-bottom");
    if (width === 1024 && height === 320 && await sidebarFooter.isVisible()) {
      await sidebarFooter.scrollIntoViewIfNeeded();
      await expect(sidebarFooter).toBeInViewport();
    }
    await page.screenshot({path:info.outputPath(`${name}-${width}x${height}.png`), animations:"disabled"});
  });
}

for (const width of [390,1440]) for (const theme of themes) {
  test(`lower page content ${width} ${theme}`, async ({page}) => {
    await setup(page, "home", "/", "zh", theme, width);
    await page.locator(".capabilities-section").scrollIntoViewIfNeeded();
    await ready(page, "home", "zh");
    await expect(page).toHaveScreenshot(`home-capabilities-${width}-${theme}.png`);
    await page.getByRole("button", {name:"后台排队，回来继续"}).click();
    await expect(page.getByText("任务状态会被保留，回来时从上次进度继续，不必守着页面等待")).toBeVisible();
    await page.locator("#examples").scrollIntoViewIfNeeded();
    await ready(page, "home", "zh");
    await expect(page).toHaveScreenshot(`home-examples-${width}-${theme}.png`);
    await page.goto("/api/docs#upload");
    await ready(page,"docs","zh");
    await expect(page.locator("#upload")).toBeVisible();
    await expect(page).toHaveScreenshot(`docs-upload-${width}-${theme}.png`);
  });
}

for (const locale of locales) for (const theme of themes) {
  test(`sidebar pinned collapsed and hover ${locale} ${theme}`, async ({page}) => {
    const zh = locale === "zh";
    await setup(page, "list", "/workspace/tasks", locale, theme, 1440);
    await page.getByRole("button", {name:zh ? "收起侧边栏" : "Collapse sidebar"}).click();
    await expect(page.locator(".workspace-sidebar")).toBeHidden();
    await expect(page).toHaveScreenshot(`sidebar-collapsed-${locale}-${theme}.png`);
    const expand = page.getByRole("button", {name:zh ? "展开侧边栏" : "Expand sidebar"});
    await expand.hover();
    await expect(page.locator(".workspace-sidebar.is-floating")).toBeVisible();
    await expect(page).toHaveScreenshot(`sidebar-hover-${locale}-${theme}.png`);
    await expand.click();
    await expect(page.locator(".workspace-shell")).not.toHaveClass(/is-collapsed/);
    await expect(page).toHaveScreenshot(`sidebar-pinned-${locale}-${theme}.png`);
    await page.getByRole("button", {name:zh ? "筛选" : "Filter", exact:true}).click();
    await expect(page).toHaveScreenshot(`task-filters-${locale}-${theme}.png`);
    await page.keyboard.press("Escape");
    await expect(page.getByRole("button", {name:zh ? "筛选" : "Filter", exact:true})).toBeFocused();
  });
}

for (const width of [390,1440]) for (const theme of themes) {
  test(`result tabs and real homepage footage ${width} ${theme}`, async ({page}) => {
    await setup(page, "detail", "/workspace/tasks/task-1", "zh", theme, width);
    await page.locator(".result-insights-panel").scrollIntoViewIfNeeded();
    for (const [label, slug] of [["概览","summary"],["时间线","timeline"],["JSON","json"]]) {
      await page.getByRole("tab", {name:label,exact:true}).click();
      await expect(page).toHaveScreenshot(`result-${slug}-${width}-${theme}.png`);
    }
    await page.goto("/");
    await page.locator(".hero-preview-wrap").scrollIntoViewIfNeeded();
    await ready(page, "home", "zh");
    await expect(page).toHaveScreenshot(`home-real-preview-${width}-${theme}.png`);
    await page.getByRole("button", {name:"动作与投篮，分别求证"}).click();
    await page.locator(".model-evidence").scrollIntoViewIfNeeded();
    await ready(page, "home", "zh");
    await expect(page).toHaveScreenshot(`home-model-output-${width}-${theme}.png`);
  });
}

for (const width of [390,1440]) for (const locale of locales) for (const theme of themes) {
  test(`key dialogs ${width} ${locale} ${theme}`, async ({page}) => {
    const zh = locale === "zh";
    await page.route("**/api/v1/api-keys", route => route.request().method() === "POST"
      ? route.fulfill({status:201, json:{...keys[0], id:"key-2", name:"Review", secret:"dsb_live_visual_fixture_only"}})
      : route.fulfill({status:200, json:keys}));
    await setup(page,"keys","/api/keys",locale,theme,width);
    await page.getByRole("button",{name:zh ? "创建 API 密钥" : "Create API key",exact:true}).click();
    await page.getByLabel(zh ? "密钥名称" : "Key name").fill("Review");
    await expect(page).toHaveScreenshot(`key-create-${width}-${locale}-${theme}.png`);
    await page.getByRole("button",{name:zh ? "创建密钥" : "Create key",exact:true}).click();
    await expect(page.getByRole("dialog",{name:zh ? "保存新密钥" : "Save your new key"})).toBeVisible();
    await expect(page).toHaveScreenshot(`key-secret-${width}-${locale}-${theme}.png`);
    await page.getByRole("button",{name:zh ? "我已保存" : "I saved it"}).click();
    await page.getByRole("button",{name:zh ? "撤销 Production" : "Revoke Production"}).click();
    await expect(page).toHaveScreenshot(`key-revoke-${width}-${locale}-${theme}.png`);
  });
  test(`empty states and navigation ${width} ${locale} ${theme}`, async ({page}) => {
    const zh = locale === "zh";
    await setup(page,"list","/workspace/tasks",locale,theme,width);
    await page.getByRole("button",{name:zh ? /^删除/ : /^Delete/}).click();
    await expect(page.getByRole("dialog")).toBeVisible();
    await expect(page).toHaveScreenshot(`task-delete-${width}-${locale}-${theme}.png`);
    await page.keyboard.press("Escape");
    await page.route("**/api/v1/tasks?**", route => route.fulfill({status:200,json:{items:[],total:0,page:1,page_size:10}}));
    await page.reload();
    await expect(page.locator(".task-list-page .workspace-state")).toBeVisible();
    await expect(page).toHaveScreenshot(`tasks-empty-${width}-${locale}-${theme}.png`);
    if (width === 390) {
      await page.getByRole("button",{name:zh ? "打开工作台菜单" : "Open workspace menu"}).click();
      await expect(page).toHaveScreenshot(`workspace-drawer-${locale}-${theme}.png`);
      await page.keyboard.press("Escape");
    }
    await page.route("**/api/v1/api-keys", route => route.fulfill({status:200,json:[]}));
    await page.goto("/api/keys");
    await expect(page.locator(".api-key-empty")).toBeVisible();
    await expect(page).toHaveScreenshot(`keys-empty-${width}-${locale}-${theme}.png`);
    await page.goto("/api/docs");
    if (width === 390) {
      await page.getByRole("button",{name:zh ? "本文目录" : "On this page",exact:true}).click();
      await expect(page).toHaveScreenshot(`docs-toc-${locale}-${theme}.png`);
      await page.locator(".public-menu-toggle").click();
      await expect(page).toHaveScreenshot(`public-menu-${locale}-${theme}.png`);
    }
  });
}

for (const width of [320,390]) for (const theme of themes) {
  test(`filter popover fits narrow viewport ${width} ${theme}`, async ({page}) => {
    await setup(page, "list", "/workspace/tasks", "zh", theme, width, 480);
    await page.getByRole("button", {name:"筛选",exact:true}).click();
    const popover = page.locator(".task-filter-popover");
    const bounds = await popover.boundingBox();
    expect(bounds).not.toBeNull();
    expect(bounds!.x).toBeGreaterThanOrEqual(0);
    expect(bounds!.x + bounds!.width).toBeLessThanOrEqual(width);
    expect(bounds!.y + bounds!.height).toBeLessThanOrEqual(480);
    await expect(page).toHaveScreenshot(`task-filters-${width}-${theme}.png`);
    await page.getByRole("button", {name:"重置",exact:true}).click();
    await page.getByRole("button", {name:"确认：应用筛选"}).click();
    await expect(popover).toBeHidden();
  });
}

for (const width of [390, 1440]) for (const locale of locales) for (const theme of themes) {
  test(`account menu ${width} ${locale} ${theme}`, async ({page}) => {
    await setup(page, "home", "/", locale, theme, width);
    if (width < 768) await page.locator(".public-menu-toggle").click();
    await page.locator(".account-link").click();
    await expect(page.locator(".account-dropdown")).toBeVisible();
    await expect(page).toHaveScreenshot(`account-menu-${width}-${locale}-${theme}.png`, { animations: "disabled", maxDiffPixelRatio: 0.001 });
  });
}
