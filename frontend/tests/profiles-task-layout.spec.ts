import { expect, test } from "@playwright/test";

const profile = { id: "p1", kind: "player", name: "Alex", goals: "Balance and footwork ".repeat(12), notes: "Left-handed", created_at: "2026-09-05T01:00:00Z", updated_at: "2026-09-05T01:00:00Z" };
const task = { id: "t1", title: "Evening practice", mode: "quick", source_type: "upload", preset_id: null, status: "failed", progress: 42, stage_message: "", error_code: null, error_message: null, submitted_at: null, created_via: "tasks_api", retry_count: 0, created_at: "2026-09-05T01:00:00Z", updated_at: "2026-09-05T01:00:00Z", started_at: null, completed_at: null, inputs: [] };

for (const width of [320, 390, 768, 1440, 1920]) for (const locale of ["zh", "en"]) for (const theme of ["light", "dark"]) {
  test(`profiles and task table ${width} ${locale} ${theme}`, async ({ page }) => {
    await page.setViewportSize({ width, height: 900 });
    await page.addInitScript(({ locale, theme }) => { localStorage.setItem("dashanbing-locale", locale); localStorage.setItem("dashanbing-theme", theme); }, { locale, theme });
    let emptyProfiles = false; let emptyTasks = false;
    await page.route("**/api/v1/**", route => {
      const url = new URL(route.request().url());
      const data = url.pathname.endsWith("/users/me") ? { id: 7, username: "coach", email: "coach@example.com", is_active: true }
        : url.pathname.endsWith("/training-profiles") ? (emptyProfiles ? [] : [profile])
        : url.pathname.endsWith("/tasks") ? { items: (url.searchParams.has("q") || emptyTasks) ? [] : [task], total: (url.searchParams.has("q") || emptyTasks) ? 0 : 1, page: 1, page_size: 10 }
        : [];
      return route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(data) });
    });
    const noPageOverflow = async () => expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    const centeredState = async () => {
      const state = page.locator(".workspace-state");
      const stateBox = (await state.boundingBox())!;
      const titleBox = (await state.locator("h2").boundingBox())!;
      expect(Math.abs(stateBox.x + stateBox.width / 2 - titleBox.x - titleBox.width / 2)).toBeLessThan(2);
    };
    await page.goto("/workspace/profiles");
    await expect(page.getByRole("table")).toBeVisible();
    await noPageOverflow();
    const profileHead = await page.locator("th").first().evaluate(element => ({ height: element.getBoundingClientRect().height, fontSize: getComputedStyle(element).fontSize }));
    expect(profileHead).toEqual({ height: 44, fontSize: "14px" });
    expect((await page.locator("tbody tr").boundingBox())!.height).toBe(68);
    await page.getByRole("button", { name: locale === "zh" ? "新建档案" : "New profile", exact: true }).click();
    const dialog = page.getByRole("dialog");
    await expect(dialog).toBeVisible();
    const box = (await dialog.boundingBox())!;
    expect(box.x).toBeGreaterThanOrEqual(0); expect(box.x + box.width).toBeLessThanOrEqual(width);
    await expect(dialog.getByLabel(locale === "zh" ? "名称" : "Name", { exact: true })).toBeFocused();
    await page.keyboard.press("Escape");
    await expect(dialog).toHaveCount(0);
    await expect(page.getByRole("button", { name: locale === "zh" ? "新建档案" : "New profile", exact: true })).toBeFocused();
    await page.getByRole("link", { name: "Alex", exact: true }).click();
    await expect(page.locator(".profile-history .workspace-state")).toBeVisible();
    await centeredState(); await noPageOverflow();
    emptyProfiles = true;
    await page.goto("/workspace/profiles");
    await expect(page.locator(".workspace-state button")).toBeVisible();
    await centeredState(); await noPageOverflow();
    await page.goto("/workspace/tasks");
    await expect(page.getByRole("table")).toBeVisible();
    await noPageOverflow();
    const progressColumn = (await page.locator("th").nth(3).boundingBox())!;
    expect(progressColumn.width).toBeGreaterThanOrEqual(180);
    expect((await page.locator("th").last().boundingBox())!.width).toBe(128);
    const bar = (await page.locator(".mini-progress").boundingBox())!;
    const percent = (await page.locator(".task-progress > span").boundingBox())!;
    expect(Math.abs(bar.y + bar.height / 2 - percent.y - percent.height / 2)).toBeLessThan(1);
    expect((await page.locator("tbody tr").boundingBox())!.height).toBe(68);
    await page.goto("/workspace/tasks?q=missing");
    await expect(page.locator(".workspace-state button")).toBeVisible();
    await centeredState();
    await page.getByRole("button", { name: locale === "zh" ? "清除筛选" : "Clear filters" }).click();
    await expect(page.getByRole("table")).toBeVisible();
    emptyTasks = true;
    await page.goto("/workspace/tasks");
    await expect(page.locator(".workspace-state a")).toHaveAttribute("href", "/workspace/new");
    await centeredState(); await noPageOverflow();
  });
}
