import { expect, test } from "@playwright/test";
const statuses = ["draft", "uploading", "queued", "running", "canceling", "completed", "failed", "canceled", "expired"];
const labels = {
  zh: ["草稿", "上传中", "排队中", "分析中", "正在取消", "已完成", "失败", "已取消", "已过期"],
  en: ["Draft", "Uploading", "Queued", "Running", "Canceling", "Completed", "Failed", "Canceled", "Expired"],
};
for (const theme of ["light", "dark"] as const) for (const locale of ["zh", "en"] as const) {
  test(`task status colors and centered symbols ${locale} ${theme}`, async ({ page }, testInfo) => {
    await page.addInitScript(({ theme, locale }) => {
      localStorage.setItem("dashanbing-theme", theme);
      localStorage.setItem("dashanbing-locale", locale);
    }, { theme, locale });
    const tasks = statuses.map((status, i) => ({
      id: `status-${status}`, title: `Demo ${i + 1}`, mode: "quick", source_type: "upload", preset_id: null,
      status: status === "canceling" ? "running" : status, stage_message: status === "canceling" ? "正在取消" : "",
      progress: status === "completed" ? 100 : 0, inputs: [], error_code: null, error_message: null,
      created_at: "2026-09-05T01:00:00Z", updated_at: "2026-09-05T01:00:00Z", submitted_at: null, started_at: null, completed_at: null,
    }));
    await page.route("**/api/v1/**", (route) => {
      const path = new URL(route.request().url()).pathname;
      const body = path === "/api/v1/users/me" ? { id: 7, username: "coach", email: "coach@example.com", is_active: true }
        : path === "/api/v1/tasks" ? { items: tasks, total: tasks.length, page: 1, page_size: 20 }
        : tasks.find((task) => path === `/api/v1/tasks/${task.id}`);
      return route.fulfill({ status: body ? 200 : 404, contentType: "application/json", body: JSON.stringify(body ?? {}) });
    });
    await page.goto("/workspace/tasks");
    const chips = page.locator(".task-table .status-chip");
    await expect(chips).toHaveCount(9);
    await expect(chips).toHaveText(labels[locale]);
    expect(new Set(await chips.evaluateAll((nodes) => nodes.map((node) => getComputedStyle(node).color))).size).toBe(9);
    expect(new Set(await chips.locator("svg").evaluateAll((nodes) => nodes.map((node) => node.innerHTML))).size).toBe(9);
    const checkSymbols = async () => {
      for (const chip of await page.locator(".status-chip").all()) {
        const symbol = chip.locator(".status-symbol");
        const circle = await symbol.boundingBox(), glyph = await symbol.locator("svg").boundingBox();
        expect(circle).not.toBeNull(); expect(glyph).not.toBeNull();
        expect(Math.abs(circle!.x + circle!.width / 2 - glyph!.x - glyph!.width / 2)).toBeLessThan(.1);
        expect(Math.abs(circle!.y + circle!.height / 2 - glyph!.y - glyph!.height / 2)).toBeLessThan(.1);
        expect(circle!.width).toBe(circle!.height);
        const color = await chip.evaluate((node) => getComputedStyle(node).color);
        expect(await symbol.evaluate((node) => getComputedStyle(node).backgroundColor)).toBe(color);
        const contrast = await chip.evaluate((node) => {
          const luminance = (css: string) => {
            const values = css.match(/[\d.]+/g)!.slice(0, 3).map(Number).map((v) => v / 255).map((v) => v <= .04045 ? v / 12.92 : ((v + .055) / 1.055) ** 2.4);
            return values[0] * .2126 + values[1] * .7152 + values[2] * .0722;
          };
          let parent: Element | null = node;
          let background = "rgb(255, 255, 255)";
          while (parent) {
            const candidate = getComputedStyle(parent).backgroundColor;
            if (candidate !== "rgba(0, 0, 0, 0)" && candidate !== "transparent") { background = candidate; break; }
            parent = parent.parentElement;
          }
          const a = luminance(getComputedStyle(node).color), b = luminance(background);
          return (Math.max(a, b) + .05) / (Math.min(a, b) + .05);
        });
        expect(contrast, await chip.getAttribute("class") ?? "status contrast").toBeGreaterThanOrEqual(4.5);
        const label = chip.locator(".status-label");
        if (await label.count()) expect(await label.evaluate((node) => getComputedStyle(node).color)).toBe(color);
      }
    };
    await checkSymbols();
    await page.screenshot({ path: testInfo.outputPath("statuses.png"), fullPage: true });
    await testInfo.attach("all task states", { path: testInfo.outputPath("statuses.png"), contentType: "image/png" });
    await page.goto("/workspace/tasks/status-canceling");
    await expect(page.locator(".detail-actions .status-chip")).toHaveText(labels[locale][4]);
    await checkSymbols();
  });
}
