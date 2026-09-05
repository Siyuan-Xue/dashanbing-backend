import { fileURLToPath } from "node:url";
import { expect, test } from "@playwright/test";

const authUser = { id: 7, username: "coach", email: "coach@example.com", is_active: true };
const baseTask = {
  id: "task-1", title: "周三投篮训练", mode: "quick", source_type: "upload", preset_id: null, status: "completed", progress: 100,
  stage_message: "已完成", error_code: null, error_message: null, submitted_at: "2026-09-05T01:05:00Z", created_via: "tasks_api", retry_count: 0,
  created_at: "2026-09-05T01:00:00Z", updated_at: "2026-09-05T02:00:00Z", started_at: "2026-09-05T01:06:00Z", completed_at: "2026-09-05T02:00:00Z", inputs: [],
};
const presets = [
  { id: "quick-demo", title: "快速演示", description: "4 次跳投", expected_minutes: 9.4 },
  { id: "mixed-actions", title: "混合动作", description: "三威胁与跳投", expected_minutes: 26.7 },
  { id: "verified-outcome", title: "命中验证", description: "带投篮结果真值的罚篮样例", expected_minutes: 30.9 },
  { id: "layup-demo", title: "上篮演示", description: "6 次上篮", expected_minutes: 14.3 },
];
const result = {
  registered_participant_count: 2,
  action_counts: { triple_threat: 1, free_throw: 0, jump_shot: 4, layup: 1 }, unsupported_event_count: 0,
  shots: { attempts: 5, makes: 3, misses: 1, undetermined: 1, make_rate: 0.6, unlinked_outcomes: 0 },
  events: [{ event_index: 1, action_type: "jump_shot", start_ms: 1000, end_ms: 2200, time_ms: 1800, result: "make" }],
  media: { phases: "/api/v1/tasks/task-1/media/phases", cam_01: "/api/v1/tasks/task-1/media/cam_01", cam_02: "/api/v1/tasks/task-1/media/cam_02", cam_03: "/api/v1/tasks/task-1/media/cam_03", cam_04: "/api/v1/tasks/task-1/media/cam_04" },
  warnings: [], disclaimer: "AI 识别结果，仅供训练复盘。",
};

test.beforeEach(async ({ page }) => {
  await page.route("**/api/v1/**", async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    const path = url.pathname;
    if (path === "/api/v1/users/me") return route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(authUser) });
    if (path === "/api/v1/presets") return route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(presets) });
    if (path === "/api/v1/tasks/task-1") return route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(baseTask) });
    if (path === "/api/v1/tasks/task-1/result") return route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(result) });
    if (path === "/api/v1/account/usage") return route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ submitted_today: { used: 4, limit: 20 }, unfinished_tasks: { used: 2, limit: 5 }, drafts: { used: 1, limit: 3 }, active_api_keys: { used: 2, limit: 5 }, retention: { drafts: "24 hours", enrollment_data: "7 days", raw_inputs: "30 days", results: "180 days" } }) });
    if (path === "/api/v1/tasks") return route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ items: [baseTask], total: 1, page: Number(url.searchParams.get("page") || 1), page_size: Number(url.searchParams.get("page_size") || 10) }) });
    if (path.includes("/media/")) return route.fulfill({ status: 200, contentType: "video/mp4", body: "" });
    return route.fulfill({ status: 404, contentType: "application/json", body: JSON.stringify({ detail: "Not found" }) });
  });
});

test("workspace shell has the fixed desktop rail and a usable phone drawer", async ({ page }, testInfo) => {
  await page.goto("/workspace/new");
  await expect(page.getByRole("heading", { name: "创建分析任务" })).toBeVisible();
  await expect(page.getByTestId("preset-card")).toHaveCount(4);

  if (testInfo.project.name === "mobile-chromium") {
    await expect(page.locator(".workspace-mobile-actions")).toHaveCount(0);
    await expect(page.getByRole("navigation", { name: "工作台导航", exact: true })).toHaveCount(0);
    const before = await page.locator(".workspace-sidebar").boundingBox();
    expect(before).not.toBeNull();
    expect(before!.x + before!.width).toBeLessThanOrEqual(1);
    await page.getByRole("button", { name: "打开工作台菜单" }).click();
    const drawer = page.getByRole("dialog", { name: "工作台导航" });
    const drawerNav = page.getByRole("navigation", { name: "工作台导航", exact: true });
    await expect(drawerNav).toBeVisible();
    await expect(page.getByRole("link", { name: "GitHub" })).toHaveAttribute("href", "https://github.com/Siyuan-Xue/dashanbing-backend");
    await expect.poll(async () => (await page.locator(".workspace-sidebar").boundingBox())?.x).toBeGreaterThanOrEqual(0);
    await expect(drawerNav.getByRole("link", { name: "创建任务" })).toBeFocused();
    await page.keyboard.press("Shift+Tab");
    await expect(drawer.getByRole("button", { name: "关闭工作台菜单" })).toBeFocused();
    await page.keyboard.press("Shift+Tab");
    await expect(drawer.getByRole("link", { name: "大山冰首页" })).toBeFocused();
    await page.keyboard.press("Shift+Tab");
    await expect(drawer.getByRole("link", { name: "设置" })).toBeFocused();
    await page.keyboard.press("Tab");
    await expect(drawer.getByRole("link", { name: "大山冰首页" })).toBeFocused();
    await page.keyboard.press("Tab");
    await expect(drawer.getByRole("button", { name: "关闭工作台菜单" })).toBeFocused();
    await drawer.getByRole("button", { name: "关闭工作台菜单" }).click();
    await expect(drawer).toHaveCount(0);
    await expect(page.getByRole("button", { name: "打开工作台菜单" })).toBeFocused();
    await page.getByRole("button", { name: "打开工作台菜单" }).click();
    await page.getByRole("dialog", { name: "工作台导航" }).getByRole("link", { name: "设置" }).click();
    await expect(page).toHaveURL(/\/workspace\/settings$/);
    await expect(page.getByRole("dialog", { name: "工作台导航" })).toHaveCount(0);
    await expect(page.getByRole("button", { name: "打开工作台菜单" })).toBeFocused();
    await page.getByRole("button", { name: "打开工作台菜单" }).click();
    await page.getByRole("dialog", { name: "工作台导航" }).getByRole("link", { name: "周三投篮训练" }).click();
    await expect(page).toHaveURL(/\/workspace\/tasks\/task-1$/);
    await expect(page.getByRole("dialog", { name: "工作台导航" })).toHaveCount(0);
    await expect(page.getByRole("button", { name: "打开工作台菜单" })).toBeFocused();
    await page.getByRole("button", { name: "打开工作台菜单" }).click();
    await drawerNav.getByRole("link", { name: "任务列表" }).click();
    await expect(page).toHaveURL(/\/workspace\/tasks$/);
    await expect(page.getByRole("button", { name: "打开工作台菜单" })).toBeFocused();
    await page.getByRole("button", { name: "打开工作台菜单" }).click();
    await page.keyboard.press("Escape");
    await expect(page.getByRole("button", { name: "打开工作台菜单" })).toBeFocused();
    await page.getByRole("button", { name: "打开工作台菜单" }).click();
    await page.getByRole("dialog", { name: "工作台导航" }).getByRole("link", { name: "创建任务" }).click();
    await expect(page).toHaveURL(/\/workspace\/new$/);
    await expect(page.getByRole("dialog", { name: "工作台导航" })).toHaveCount(0);
    await expect(page.getByRole("button", { name: "打开工作台菜单" })).toBeFocused();
    await page.getByRole("button", { name: "打开工作台菜单" }).click();
    await page.getByRole("dialog", { name: "工作台导航" }).getByRole("link", { name: /coach/ }).click();
    await expect(page).toHaveURL(/\/workspace\/settings$/);
    await expect(page.getByRole("dialog", { name: "工作台导航" })).toHaveCount(0);
    await expect(page.getByRole("button", { name: "打开工作台菜单" })).toBeFocused();
    await page.getByRole("button", { name: "打开工作台菜单" }).click();
    await page.getByRole("dialog", { name: "工作台导航" }).getByRole("link", { name: "大山冰首页" }).click();
    await expect(page).toHaveURL(/\/$/);
    await expect(page.getByRole("dialog", { name: "工作台导航" })).toHaveCount(0);
  } else {
    await expect(page.getByRole("link", { name: "GitHub" })).toHaveAttribute("href", "https://github.com/Siyuan-Xue/dashanbing-backend");
    const sidebar = await page.locator(".workspace-sidebar").boundingBox();
    expect(sidebar?.width).toBe(260);
    const footer = await page.locator(".workspace-sidebar-bottom").boundingBox();
    expect(footer?.height).toBe(48);
    const account = await page.getByRole("link", { name: "账户：coach" }).boundingBox();
    const github = await page.getByRole("link", { name: "GitHub" }).boundingBox();
    expect(account?.y).toBe(github?.y);
    await page.getByRole("button", { name: "收起侧边栏" }).click();
    await expect(page.locator(".workspace-sidebar")).toBeHidden();
    await expect(page.locator(".workspace-main")).toHaveCSS("margin-left", "0px");
    await expect(page.locator(".workspace-collapsed-header .brand")).toBeVisible();
    const fullWidth = (await page.locator(".workspace-main").boundingBox())!.width;
    const expand = page.getByRole("button", { name: "展开侧边栏" });
    await expand.hover();
    await expect(page.locator(".workspace-sidebar.is-floating")).toBeVisible();
    expect((await page.locator(".workspace-main").boundingBox())!.width).toBe(fullWidth);
    await page.getByRole("navigation", { name: "工作台导航" }).hover();
    await expect(page.locator(".workspace-sidebar.is-floating")).toBeVisible();
    await page.locator(".workspace-main").hover({ position: { x: 500, y: 20 } });
    await expect(page.locator(".workspace-sidebar")).toBeHidden();
    await expand.focus();
    await page.keyboard.press("ArrowDown");
    await expect(page.getByRole("link", { name: "创建任务" })).toBeFocused();
    await page.keyboard.press("Escape");
    await expect(expand).toBeFocused();
    await expect(page.locator(".workspace-sidebar")).toBeHidden();
    await page.keyboard.press("ArrowDown");
    await page.getByRole("link", { name: "账户：coach" }).click();
    await expect(page).toHaveURL(/\/workspace\/settings$/);
    await expect(page.getByRole("button", { name: "展开侧边栏" })).toHaveAttribute("aria-expanded", "false");
    await page.getByRole("button", { name: "展开侧边栏" }).click();
    expect((await page.locator(".workspace-sidebar").boundingBox())?.width).toBe(260);
    await expect(page.getByRole("navigation", { name: "工作台导航", exact: true })).toBeVisible();
  }

  const dimensions = await page.evaluate(() => ({ viewport: innerWidth, page: document.documentElement.scrollWidth }));
  expect(dimensions.page).toBeLessThanOrEqual(dimensions.viewport);
});

test("task list filters through the real query contract and detail switches media", async ({ page }, testInfo) => {
  test.skip(testInfo.project.name !== "desktop-chromium", "desktop interaction coverage");
  let observed = "";
  await page.route("**/api/v1/tasks?**", async (route) => {
    const url = new URL(route.request().url());
    if (url.searchParams.get("page_size") !== "5") observed = url.search;
    await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ items: [baseTask], total: 21, page: Number(url.searchParams.get("page") || 1), page_size: Number(url.searchParams.get("page_size") || 10) }) });
  });
  await page.goto("/workspace/tasks");
  await page.getByRole("searchbox", { name: "搜索任务" }).fill("周三");
  await page.getByRole("button", { name: "筛选", exact: true }).click();
  await page.getByLabel("状态").selectOption("completed");
  await page.getByLabel("分析模式").selectOption("quick");
  await page.getByRole("button", { name: "确认：应用筛选" }).click();
  await expect(page).toHaveURL(/q=%E5%91%A8%E4%B8%89&status=completed&mode=quick&page=1&page_size=10/);
  await expect.poll(() => observed).toContain("q=%E5%91%A8%E4%B8%89");
  await page.getByRole("link", { name: "周三投篮训练" }).first().click();
  await expect(page.getByRole("tab", { name: "阶段合成" })).toHaveAttribute("aria-selected", "true");
  const cameraRequest = page.waitForRequest("**/tasks/task-1/media/cam_01");
  await page.getByRole("tab", { name: "机位 1" }).click();
  await cameraRequest;
  await expect(page.getByRole("tab", { name: "机位 1" })).toHaveAttribute("aria-selected", "true");
  await expect(page.getByRole("button", { name: "重新加载视频" })).toBeVisible();
  await expect(page.getByRole("link", { name: "下载 JSON 结果" })).toBeVisible();
});

test("staged browser upload recovers one failed slot and gates submission", async ({ page }, testInfo) => {
  test.skip(testInfo.project.name !== "desktop-chromium", "desktop upload interaction coverage");
  const inputs: Array<Record<string, unknown>> = [];
  let camOneAttempts = 0;
  const draft = () => ({ ...baseTask, status: "draft", progress: 0, submitted_at: null, started_at: null, completed_at: null, inputs });
  await page.route("**/api/v1/tasks", async (route) => {
    if (route.request().method() !== "POST") return route.fallback();
    await route.fulfill({ status: 201, contentType: "application/json", body: JSON.stringify(draft()) });
  });
  await page.route("**/api/v1/tasks/task-1/inputs/*", async (route) => {
    const slot = new URL(route.request().url()).pathname.split("/").at(-1)!;
    if (slot === "cam_01" && camOneAttempts++ === 0) {
      return route.fulfill({ status: 400, contentType: "application/json", body: JSON.stringify({ detail: "Invalid video" }) });
    }
    const multipart = route.request().postDataBuffer()?.toString() || "";
    const filename = multipart.match(/filename="([^"]+)"/)?.[1] || `${slot}.mp4`;
    inputs.splice(0, inputs.length, ...inputs.filter((item) => item.slot !== slot), { slot, original_filename: filename, byte_size: 5, validation_state: "valid", created_at: baseTask.created_at, updated_at: baseTask.updated_at });
    await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(draft()) });
  });
  await page.route("**/api/v1/tasks/task-1/submit", async (route) => route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ ...draft(), status: "queued" }) }));

  await page.goto("/workspace/new");
  const submit = page.getByRole("button", { name: "提交分析" });
  await expect(submit).toBeDisabled();
  await page.getByLabel("任务标题").fill("周三投篮训练");
  await page.getByLabel("注册视频").setInputFiles({ name: "enroll.mp4", mimeType: "video/mp4", buffer: Buffer.from("video") });
  await page.getByLabel("机位 1").setInputFiles({ name: "cam1.mp4", mimeType: "video/mp4", buffer: Buffer.from("video") });
  await expect(page.getByRole("alert")).toContainText("Invalid video");
  await expect(submit).toBeDisabled();
  await page.getByRole("button", { name: "重试机位 1" }).click();
  await expect(page.getByText("cam1.mp4")).toBeVisible();
  await page.getByLabel("机位 2").setInputFiles({ name: "cam2.mp4", mimeType: "video/mp4", buffer: Buffer.from("video") });
  await page.getByLabel("机位 3").setInputFiles({ name: "cam3.mp4", mimeType: "video/mp4", buffer: Buffer.from("video") });
  await page.getByLabel("机位 4").setInputFiles({ name: "cam4.mp4", mimeType: "video/mp4", buffer: Buffer.from("video") });
  await expect(submit).toBeEnabled();
  await submit.click();
  await expect(page).toHaveURL(/\/workspace\/tasks\/task-1$/);
});

test("settings preferences remain functional inside the mobile-safe shell", async ({ page }) => {
  await page.goto("/workspace/settings");
  await expect(page.getByText("4 / 20")).toBeVisible();
  await page.getByRole("button", { name: "English" }).click();
  await expect(page.getByRole("heading", { name: "Settings" })).toBeVisible();
  await page.getByRole("button", { name: "Switch to dark theme" }).click();
  await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");
  const dimensions = await page.evaluate(() => ({ viewport: innerWidth, page: document.documentElement.scrollWidth }));
  expect(dimensions.page).toBeLessThanOrEqual(dimensions.viewport);
});

for (const width of [320, 390, 767, 768, 1024, 1279, 1280, 1440, 1920]) {
  test(`workspace panels and footer remain usable at ${width}px`, async ({ page }, testInfo) => {
    test.skip(testInfo.project.name !== "desktop-chromium", "explicit viewport coverage");
    await page.setViewportSize({ width, height: 900 });
    const english = width === 320 || width === 1024;
    await page.addInitScript(({ english }) => {
      localStorage.setItem("dashanbing-locale", english ? "en" : "zh");
      localStorage.setItem("dashanbing-theme", english ? "dark" : "light");
    }, { english });
    await page.route("**/api/v1/presets/quick-demo/result", (route) => route.fulfill({ json: result }));
    for (const path of ["new", "tasks", "tasks/task-1", "examples/quick-demo", "settings"]) {
      await page.goto(`/workspace/${path}`);
      await expect(page.locator(".workspace-page h1")).toBeVisible();
      const main = page.locator(".workspace-main");
      await expect(main).toHaveCSS("overflow-x", "visible");
      await expect(page.locator(".workspace-page")).toHaveCSS("border-radius", "0px");
      await expect(page.locator(".workspace-page")).toHaveCSS("border-top-width", "0px");
      await expect(main).toHaveCSS("padding", "0px");
      expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(width);
      if (path === "new") {
        await expect(page.locator('input[type="file"]')).toHaveCount(5);
        if (width >= 768) {
          const sidebar = page.locator(".workspace-sidebar");
          const expand = page.getByRole("button", { name: english ? "Expand sidebar" : "展开侧边栏" });
          if (await expand.count()) await expand.click();
          expect((await sidebar.boundingBox())?.width).toBe(260);
          expect((await page.locator(".workspace-sidebar-bottom").boundingBox())?.height).toBe(48);
          const account = await page.getByRole("link", { name: /coach/ }).boundingBox();
          const github = await page.getByRole("link", { name: "GitHub" }).boundingBox();
          expect(account?.y).toBe(github?.y);
          expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(width);
        }
      }
      if (path === "tasks") {
        await expect(page.getByRole("table")).toBeVisible();
        const table = page.locator(".task-table-wrap");
        const scrolled = await table.evaluate((element) => { element.scrollLeft = 10000; return element.scrollLeft; });
        if (width < 768) expect(scrolled).toBeGreaterThan(0);
      }
      if (path.includes("task-1") || path.includes("quick-demo")) {
        await expect(page.locator(".result-summary")).toBeVisible();
        const summaryHeight = (await page.locator(".result-workspace").boundingBox())!.height;
        const overviewHeight = (await page.locator(".insight-content").boundingBox())!.height;
        for (const tab of [english ? "Timeline" : "时间线", "JSON"]) {
          await page.getByRole("tab", { name: tab, exact: true }).click();
          expect((await page.locator(".result-workspace").boundingBox())!.height).toBeCloseTo(summaryHeight, 0);
          expect((await page.locator(".insight-content").boundingBox())!.height).toBeCloseTo(overviewHeight, 0);
        }
        await page.getByRole("tab", { name: "JSON", exact: true }).click();
        await expect(page.locator(".result-json")).toContainText("registered_participant_count");
        const media = (await page.locator(".result-media-panel").boundingBox())!;
        const insights = (await page.locator(".result-insights-panel").boundingBox())!;
        const stage = (await page.locator(".media-stage").boundingBox())!;
        expect(stage.x + stage.width).toBeLessThanOrEqual(media.x + media.width);
        expect(insights.y).toBeGreaterThanOrEqual(media.y + media.height);
        expect(Math.abs(insights.width - media.width)).toBeLessThan(1);
        expect(stage.width).toBeGreaterThan(media.width * .95);
        expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(width);
        await page.getByRole("tab", { name: english ? "Summary" : "概览" }).click();
      }
      if ([390, 768, 1024, 1440, 1920].includes(width)) {
        await page.screenshot({ path: testInfo.outputPath(`${path.replaceAll("/", "-")}-${width}.png`), fullPage: true, animations: "disabled" });
      }
    }
  });
}

test("long result tabs retain overview height and scroll locally", async ({ page }, testInfo) => {
  test.skip(testInfo.project.name !== "desktop-chromium", "explicit desktop and phone coverage");
  await page.route("**/api/v1/tasks/task-1/result", route => route.fulfill({ json: {
    ...result,
    events: Array.from({ length: 100 }, (_, index) => ({ ...result.events[0], event_index: index + 1 })),
    warnings: Array.from({ length: 8 }, () => "2 个事件属于当前版本未支持的动作类型。"),
  } }));
  for (const width of [390, 1440]) {
    await page.setViewportSize({ width, height: 900 });
    await page.goto("/workspace/tasks/task-1");
    await expect(page.locator(".result-summary")).toBeVisible();
    const overview = await page.locator(".insight-content").boundingBox();
    const workspace = await page.locator(".result-workspace").boundingBox();
    for (const tab of ["时间线", "JSON"]) {
      await page.getByRole("tab", { name: tab, exact: true }).click();
      expect((await page.locator(".insight-content").boundingBox())!.height).toBeCloseTo(overview!.height, 0);
      expect((await page.locator(".result-workspace").boundingBox())!.height).toBeCloseTo(workspace!.height, 0);
      await expect(page.locator(".result-summary")).toHaveAttribute("aria-hidden", "true");
      const alternate = page.locator(".insight-alternate");
      expect(await alternate.evaluate(el => el.scrollHeight > el.clientHeight)).toBe(true);
      await alternate.focus();
      await page.keyboard.press("End");
      await expect.poll(() => alternate.evaluate(el => el.scrollTop)).toBeGreaterThan(0);
    }
    await page.getByRole("tab", { name: "概览", exact: true }).click();
    await expect(page.locator(".result-summary")).toBeVisible();
    expect((await page.locator(".insight-content").boundingBox())!.height).toBeCloseTo(overview!.height, 0);
  }
});

test("resizing across the drawer breakpoint restores usable navigation and document scrolling", async ({ page }, testInfo) => {
  test.skip(testInfo.project.name !== "desktop-chromium", "explicit breakpoint coverage");
  await page.setViewportSize({ width: 768, height: 500 });
  await page.goto("/workspace/new");
  await expect(page.getByRole("button", { name: "展开侧边栏" })).toBeVisible();
  await page.setViewportSize({ width: 767, height: 500 });
  await page.getByRole("button", { name: "打开工作台菜单" }).click();
  await expect(page.getByRole("dialog", { name: "工作台导航" })).toBeVisible();
  await expect(page.locator("body")).toHaveCSS("overflow", "hidden");
  await page.setViewportSize({ width: 768, height: 500 });
  await expect(page.getByRole("dialog")).toHaveCount(0);
  await expect(page.getByRole("button", { name: "展开侧边栏" })).toBeFocused();
  await expect(page.locator("body")).not.toHaveCSS("overflow", "hidden");
  await page.setViewportSize({ width: 390, height: 320 });
  await page.getByRole("button", { name: "打开工作台菜单" }).click();
  await page.getByRole("link", { name: "设置", exact: true }).click();
  await expect(page).toHaveURL(/\/workspace\/settings$/);
  await expect(page.getByRole("button", { name: "打开工作台菜单" })).toBeFocused();
});

test("settings shows content directly and keeps preference controls usable", async ({ page }) => {
  await page.goto("/workspace/settings");
  await expect(page.getByRole("navigation", { name: "设置导航" })).toHaveCount(0);
  await expect(page.getByRole("heading", { name: "用量与配额" })).toBeVisible();
  await page.getByRole("button", { name: "English" }).scrollIntoViewIfNeeded();
  await expect(page.getByRole("button", { name: "English" })).toBeInViewport();
  await page.getByRole("button", { name: "English" }).click();
  await expect(page.getByRole("heading", { name: "Interface preferences" })).toBeVisible();
});


test("filter reset clears options on confirm while preserving search and page size", async ({ page }) => {
  await page.goto("/workspace/tasks?q=training&status=failed&mode=full&page=2&page_size=20");
  const trigger = page.getByRole("button", { name: "筛选", exact: true });
  await trigger.click();
  await expect(page.getByLabel("状态")).toHaveValue("failed");
  await page.getByRole("button", { name: "重置", exact: true }).click();
  await expect(page.getByLabel("状态")).toHaveValue("");
  await expect(page.getByLabel("分析模式")).toHaveValue("");
  await expect(page).toHaveURL(/status=failed/);
  await expect(trigger).toHaveClass(/has-filters/);
  await page.keyboard.press("Escape");
  await expect(trigger).toBeFocused();
  await trigger.click();
  await expect(page.getByLabel("状态")).toHaveValue("failed");
  await expect(page.getByLabel("分析模式")).toHaveValue("full");
  await page.getByRole("button", { name: "重置", exact: true }).click();
  await page.getByRole("button", { name: "确认：应用筛选" }).click();
  await expect(page).toHaveURL(/q=training&page=1&page_size=20$/);
  await expect(trigger).toBeFocused();
  await expect(trigger).not.toHaveClass(/has-filters/);
});


test("result videos autoplay muted inline and retain manual pause across result tabs", async ({ page }) => {
  await page.route("**/api/v1/**/media/**", route => route.fulfill({contentType:"video/webm",path:fileURLToPath(new URL("./fixtures/autoplay.webm",import.meta.url))}));
  await page.route("**/api/v1/presets/quick-demo/result", route => route.fulfill({json:{...result,media:{phases:"/api/v1/presets/quick-demo/media/phases",cam_01:"/api/v1/presets/quick-demo/media/cam_01"}}}));
  await page.goto("/workspace/tasks/task-1");
  const video=page.locator(".media-stage video");
  await expect.poll(()=>video.evaluate((v: HTMLVideoElement)=>!v.paused && v.currentTime>0.05)).toBe(true);
  await expect(video).toHaveJSProperty("muted",true);
  await expect(video).toHaveJSProperty("playsInline",true);
  await page.getByRole("tab",{name:"机位 1",exact:true}).click();
  await expect(video).toHaveAttribute("src",/cam_01$/);
  await expect.poll(()=>video.evaluate((v: HTMLVideoElement)=>!v.paused && v.currentTime>0.05)).toBe(true);
  await video.evaluate((v: HTMLVideoElement)=>v.pause());
  await page.getByRole("tab",{name:"JSON",exact:true}).click();
  await expect(video).toHaveJSProperty("paused",true);
  await page.goto("/workspace/examples/quick-demo");
  await expect.poll(()=>video.evaluate((v: HTMLVideoElement)=>!v.paused && v.currentTime>0.05)).toBe(true);
  await expect(video).toHaveJSProperty("muted",true);
});

test("detail toolbars align on desktop and fit long titles on mobile", async ({ page }, info) => {
  const title="LongTrainingSession".repeat(6);
  await page.route("**/api/v1/tasks/task-1", route => route.fulfill({json:{...baseTask,title,status:"running",progress:35,stage_message:"Analyzing actions"}}));
  await page.goto("/workspace/tasks/task-1");
  await expect(page.getByRole("heading",{name:title})).toBeVisible();
  await expect(page.getByRole("progressbar")).toHaveAttribute("aria-valuenow","35");
  const aligned = async (selector: string) => {
    const boxes=await page.locator(selector).evaluateAll(nodes=>nodes.map(n=>{const r=n.getBoundingClientRect();return {middle:r.y+r.height/2,right:r.right};}));
    expect(boxes.every(b=>b.right<= (info.project.name==="mobile-chromium"?390:1440))).toBe(true);
    if(info.project.name==="desktop-chromium")expect(Math.max(...boxes.map(b=>b.middle))-Math.min(...boxes.map(b=>b.middle))).toBeLessThan(2);
    expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
  };
  await aligned(".detail-header > div");
  await page.goto("/workspace/examples/quick-demo");
  await expect(page.getByRole("heading",{name:"快速演示"})).toBeVisible();
  await expect(page.getByRole("button",{name:"创建任务",exact:true})).toBeVisible();
  await aligned(".detail-header > div");
});


test("settings logout retains focus on failure and returns home on retry", async ({ page }) => {
  let attempts = 0;
  let releaseLogout!: () => void;
  const pendingLogout = new Promise<void>(resolve => { releaseLogout = resolve; });
  await page.route("**/api/v1/logout", async route => {
    expect(route.request().method()).toBe("POST");
    attempts += 1;
    if (attempts === 1) {
      await pendingLogout;
      return route.fulfill({ status: 503, json: { detail: "Unavailable" } });
    }
    await page.route("**/api/v1/users/me", r => r.fulfill({ status: 401, json: { detail: "Not authenticated" } }));
    return route.fulfill({ status: 204 });
  });
  // Signing out must still work when account quota data cannot load.
  await page.route("**/api/v1/account/usage", route => route.fulfill({ status: 503, json: { detail: "Unavailable" } }));
  await page.goto("/workspace/settings");
  const signOut = page.getByRole("button", { name: "退出登录", exact: true });
  await expect(signOut).toBeInViewport();
  await signOut.click();
  const pendingButton = page.getByRole("button", { name: "正在退出", exact: true });
  await expect(pendingButton).toHaveAttribute("aria-disabled", "true");
  await page.keyboard.press("Enter");
  expect(attempts).toBe(1);
  releaseLogout();
  await expect(page.getByRole("alert").filter({ hasText: "退出失败" })).toBeVisible();
  await expect(signOut).toBeFocused();
  await expect(page).toHaveURL(/\/workspace\/settings$/);
  await page.keyboard.press("Enter");
  await expect(page).toHaveURL(/\/$/);
  const menu = page.locator(".public-menu-toggle");
  if (await menu.isVisible()) {
    await expect(menu).toBeFocused();
    await menu.click();
  } else await expect(page.getByRole("link", { name: "登录", exact: true })).toBeFocused();
  await page.getByRole("link", { name: "在线使用", exact: true }).click();
  await expect(page).toHaveURL(/\/login\?next=/);
  expect(attempts).toBe(2);
});


for (const theme of ["light", "dark"]) test(`workspace navigation marks only the current destination with an accent border ${theme}`, async ({ page }) => {
    await page.addInitScript(value => localStorage.setItem("dashanbing-theme", value), theme);
    for (const path of ["new", "tasks"]) {
      await page.goto(`/workspace/${path}`);
      const toggle = page.getByRole("button", { name: "打开工作台菜单" });
      if (await toggle.isVisible()) await toggle.click();
      const nav = page.locator(".workspace-nav");
      const selected = nav.locator('[aria-current="page"]');
      await expect(selected).toHaveCount(1);
      await expect(selected).toHaveAttribute("href", `/workspace/${path}`);
      await expect(selected).toHaveCSS("border-top-width", "2px");
      await expect(selected).toHaveCSS("border-top-color", theme === "light" ? "rgb(155, 68, 54)" : "rgb(230, 165, 152)");
      await expect(selected).toHaveCSS("font-weight", "600");
      await expect(nav.locator('a:not([aria-current="page"])')).toHaveCSS("border-top-color", "rgba(0, 0, 0, 0)");
    }
});
