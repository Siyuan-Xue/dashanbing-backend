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
  await page.route("**/api/v1/**", async route => {
    const url = new URL(route.request().url());
    if (url.pathname === "/api/v1/users/me") return route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(user) });
    if (url.pathname === "/api/v1/presets") return route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(presets) });
    if (url.pathname === "/api/v1/tasks/task-1/result") return route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(result) });
    if (url.pathname === "/api/v1/tasks/task-1") return route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(task) });
    if (url.pathname === "/api/v1/tasks") return route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ items: [task], total: 1, page: 1, page_size: 10 }) });
    if (url.pathname === "/api/v1/account/usage") return route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(usage) });
    if (url.pathname === "/api/v1/api-keys") return route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(keys) });
    return route.fulfill({ status: 404, contentType: "application/json", body: JSON.stringify({ detail: "Not found" }) });
  });
});

const pages = [
  ["home", "/"], ["new", "/workspace/new"], ["list", "/workspace/tasks"],
  ["detail", "/workspace/tasks/task-1"], ["docs", "/api/docs"], ["keys", "/api/keys"],
] as const;
const locales = ["zh", "en"] as const;
const themes = ["light", "dark"] as const;

async function waitForRouteFixture(page: import("@playwright/test").Page, name: typeof pages[number][0], locale: typeof locales[number]) {
  const zh = locale === "zh";
  await expect(page.locator(".account-link, .workspace-account").filter({ hasText: "coach" })).toBeVisible();
  if (name === "home") return expect(page.getByRole("heading", { name: zh ? "让多路训练视频，变成可复盘的篮球洞察" : "Turn multi-angle training video into basketball insight you can review" })).toBeVisible();
  if (name === "new") {
    await expect(page.getByRole("heading", { name: zh ? "创建分析任务" : "Create analysis task" })).toBeVisible();
    return expect(page.getByTestId("preset-card").first()).toBeVisible();
  }
  if (name === "list") {
    await expect(page.locator(".task-list-page h1")).toHaveText(zh ? "任务列表" : "Tasks");
    return expect(page.locator(".task-table tbody .task-title-link")).toHaveText(/Friday shooting session/);
  }
  if (name === "detail") {
    await expect(page.getByRole("heading", { name: "Friday shooting session" })).toBeVisible();
    return expect(page.locator(".detail-progress small")).toHaveText(zh ? "已完成" : "Complete");
  }
  if (name === "docs") return expect(page.getByRole("heading", { name: zh ? "大山冰 API 文档" : "DaShanBing API Docs" })).toBeVisible();
  await expect(page.getByRole("heading", { name: zh ? "API 管理" : "API Management" })).toBeVisible();
  return expect(page.getByText("Production", { exact: true })).toBeVisible();
}

test("public visual readiness waits for delayed authenticated header identity", async ({ page }) => {
  let authFulfilled = false;
  await page.route("**/api/v1/users/me", async route => {
    await new Promise(resolve => setTimeout(resolve, 125));
    authFulfilled = true;
    await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(user) });
  });
  await page.goto("/");
  await waitForRouteFixture(page, "home", "zh");
  expect(authFulfilled).toBe(true);
  await expect(page.locator(".account-link, .workspace-account").filter({ hasText: "coach" })).toBeVisible();
});

for (const [name, path] of pages) for (const locale of locales) for (const theme of themes) {
  test(`visual ${name} ${locale} ${theme}`, async ({ page }, testInfo) => {
    await page.addInitScript(({ locale, theme }) => {
      localStorage.setItem("dashanbing-locale", locale);
      localStorage.setItem("dashanbing-theme", theme);
    }, { locale, theme });
    await page.emulateMedia({ reducedMotion: "reduce", colorScheme: theme });
    await page.goto(path);
    await waitForRouteFixture(page, name, locale);
    await page.evaluate(() => document.fonts.ready);
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    const viewport = testInfo.project.name === "desktop-chromium" ? "1440x900" : "phone";
    await page.screenshot({ path: testInfo.outputPath("visual-matrix", `${name}-${viewport}-${locale}-${theme}.png`), animations: "disabled" });
  });
}
