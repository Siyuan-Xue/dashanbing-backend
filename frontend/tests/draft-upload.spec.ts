import { expect, test, type Page } from "@playwright/test";

const timestamp = "2026-09-05T01:00:00Z";
const slots = ["enrollment_video", "cam_01", "cam_02", "cam_03", "cam_04"];
const validInput = (slot: string, name = `${slot}.mp4`) => ({ slot, original_filename: name, byte_size: 100, validation_state: "valid", created_at: timestamp, updated_at: timestamp });

async function server(page: Page, restored = false) {
  let task = { id: "draft-1", title: "Saved practice", mode: "quick", source_type: "upload", preset_id: null, status: "draft", progress: 0, stage_message: "Draft", error_code: null, error_message: null, submitted_at: null, created_via: "tasks_api", retry_count: 0, created_at: timestamp, updated_at: timestamp, started_at: null, completed_at: null, inputs: restored ? [validInput(slots[0])] : [] };
  let creates = 0;
  let invalidReplacement = false;
  await page.route("**/api/v1/**", async route => {
    const request = route.request();
    const path = new URL(request.url()).pathname;
    if (path === "/api/v1/users/me") return route.fulfill({ json: { id: 7, username: "coach", email: "coach@example.com", is_active: true } });
    if (path === "/api/v1/presets") return route.fulfill({ json: [] });
    if (path === "/api/v1/tasks") {
      if (request.method() === "POST") { creates++; task = { ...task, ...request.postDataJSON() }; return route.fulfill({ status: 201, json: task }); }
      return route.fulfill({ json: { items: [task], total: 1, page: 1, page_size: 20 } });
    }
    if (path === `/api/v1/tasks/${task.id}`) {
      if (request.method() === "PATCH") task = { ...task, ...request.postDataJSON() };
      return route.fulfill({ json: task });
    }
    if (path.includes("/inputs/")) {
      if (invalidReplacement) { invalidReplacement = false; return route.fulfill({ status: 400, json: { detail: "Invalid video" } }); }
      const slot = path.split("/").at(-1)!;
      const name = request.postDataBuffer()?.toString().match(/filename="([^"]+)"/)?.[1] || `${slot}.mp4`;
      task = { ...task, inputs: [...task.inputs.filter(item => item.slot !== slot), validInput(slot, name)] };
      return route.fulfill({ json: task });
    }
    if (path.endsWith("/submit")) { task.status = "queued"; task.stage_message = "Queued"; return route.fulfill({ json: task }); }
    return route.fulfill({ status: 404, json: { detail: "Not found" } });
  });
  return { get task() { return task; }, get creates() { return creates; }, failReplacement: () => { invalidReplacement = true; } };
}

for (const locale of ["zh", "en"] as const) for (const theme of ["light", "dark"] as const) {
  test(`draft uploads resume and replace ${locale} ${theme}`, async ({ page }, info) => {
    const api = await server(page);
    const zh = locale === "zh";
    await page.addInitScript(({ locale, theme }) => { localStorage.setItem("dashanbing-locale", locale); localStorage.setItem("dashanbing-theme", theme); }, { locale, theme });
    await page.goto("/workspace/new");
    const fileInputs = page.locator('input[type="file"]');
    const file = (name: string) => ({ name, mimeType: "video/mp4", buffer: Buffer.from("video") });
    await fileInputs.nth(0).setInputFiles(file("players.mp4"));
    await expect(page.getByText("players.mp4", { exact: true })).toBeVisible();
    await expect(page).toHaveURL(/\/workspace\/new\?draft=draft-1$/);
    await expect(page.getByRole("alert")).toHaveCount(0);
    await page.getByLabel(zh ? "任务标题" : "Task title").fill("Saturday practice");
    await page.getByRole("radio", { name: zh ? /完整/ : /Full/ }).check();
    await expect.poll(() => api.task.mode).toBe("full");
    await expect.poll(() => api.task.title).toBe("Saturday practice");
    await page.reload();
    await expect(page.getByLabel(zh ? "任务标题" : "Task title")).toHaveValue("Saturday practice");
    await expect(page.getByText("players.mp4", { exact: true })).toBeVisible();
    await expect(page.getByText(zh ? "点击替换" : "Click to replace", { exact: true })).toBeVisible();
    await page.goto("/workspace/tasks");
    await expect(page.locator(".task-table tbody")).toContainText("1 / 5");
    await page.getByRole("link", { name: zh ? "继续编辑" : "Continue editing", exact: true }).click();
    await expect(fileInputs).toHaveCount(5);
    api.failReplacement();
    await fileInputs.nth(0).setInputFiles(file("bad.mp4"));
    await expect(page.getByRole("alert")).toContainText("Invalid video");
    await expect(page.getByText("players.mp4", { exact: true })).toBeVisible();
    await fileInputs.nth(0).setInputFiles(file("players-new.mp4"));
    await expect(page.getByText("players-new.mp4", { exact: true })).toBeVisible();
    await expect(page.getByText("players.mp4", { exact: true })).toHaveCount(0);
    for (let index = 1; index < 5; index++) await fileInputs.nth(index).setInputFiles(file(`${slots[index]}.mp4`));
    const submit = page.getByRole("button", { name: zh ? "提交分析" : "Submit analysis", exact: true });
    await expect(submit).toBeEnabled();
    await expect(page.getByText(zh ? "点击替换" : "Click to replace", { exact: true })).toHaveCount(5);
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    await page.screenshot({ path: info.outputPath("draft-ready.png"), fullPage: true });
    await submit.click();
    await expect(page).toHaveURL(/\/workspace\/tasks\/draft-1$/);
    await expect.poll(() => api.task.status).toBe("queued");
    expect(api.creates).toBe(1);
  });
}

test("reopened uploads wait for validation and preserve completed inputs", async ({ page }) => {
  const api = await server(page, true);
  api.task.status = "uploading";
  await page.goto("/workspace/new?draft=draft-1");
  await expect(page.getByText("enrollment_video.mp4", { exact: true })).toBeVisible();
  await expect(page.getByLabel("机位 1", { exact: true })).toBeDisabled();
  api.task.status = "draft";
  await expect(page.getByLabel("机位 1", { exact: true })).toBeEnabled();
  await expect(page.getByText("enrollment_video.mp4", { exact: true })).toBeVisible();
});

test("creating another task does not reuse the previous draft", async ({ page }, info) => {
  const api = await server(page, true);
  await page.goto("/workspace/new?draft=draft-1");
  await expect(page.getByText("enrollment_video.mp4", { exact: true })).toBeVisible();
  if (info.project.name === "mobile-chromium") await page.getByRole("button", { name: "打开工作台菜单" }).click();
  await page.getByRole("link", { name: "创建任务", exact: true }).click();
  await expect(page).toHaveURL(/\/workspace\/new$/);
  await expect(page.getByLabel("任务标题")).toHaveValue("");
  await expect(page.getByText("enrollment_video.mp4", { exact: true })).toHaveCount(0);
  expect(api.creates).toBe(0);
});

for (const width of [320, 1440]) test(`restored draft layout at ${width}px`, async ({ page }, info) => {
  test.skip(info.project.name !== "desktop-chromium", "explicit viewport coverage");
  const api = await server(page, true);
  api.task.inputs = slots.map(slot => validInput(slot));
  await page.setViewportSize({ width, height: 900 });
  await page.goto("/workspace/new?draft=draft-1");
  await expect(page.getByText("点击替换", { exact: true })).toHaveCount(5);
  await expect(page.getByRole("button", { name: "提交分析" })).toBeEnabled();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await page.screenshot({ path: info.outputPath(`draft-${width}.png`), fullPage: true });
});
