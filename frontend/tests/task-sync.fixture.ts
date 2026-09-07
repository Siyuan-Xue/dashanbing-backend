import type { Page, Route } from "@playwright/test";

export async function fulfillSyncFixture(route: Route, response: Response) {
  await route.fulfill({ status: response.status, headers: Object.fromEntries(response.headers), body: Buffer.from(await response.arrayBuffer()) });
}

// Complete the new submission prerequisites through the real UI on desktop or mobile.
export async function confirmTaskSync(page: Page, locale: "zh" | "en" = "zh") {
  const zh = locale === "zh";
  await page.getByRole("combobox", { name: zh ? "注册人数" : "Number of people", exact: true }).selectOption("2");
  await page.getByRole("button", { name: zh ? "同步视频" : "Sync videos", exact: true }).click();
  const dialog = page.getByRole("dialog", { name: zh ? "同步四个机位" : "Sync four cameras", exact: true });
  const selectLabel = zh ? "选定当前帧" : "Select current frame";
  await dialog.getByRole("region", { name: zh ? "机位 3 · 基准" : "Camera 3 · Reference", exact: true }).getByRole("button", { name: selectLabel, exact: true }).click();
  for (const number of [1, 2, 4]) {
    const name = `${zh ? "机位" : "Camera"} ${number}`;
    const tab = dialog.getByRole("tab", { name, exact: true });
    if (await tab.count()) await tab.click();
    await dialog.getByRole("region", { name, exact: true }).getByRole("button", { name: selectLabel, exact: true }).click();
  }
  await dialog.getByRole("button", { name: zh ? "确认同步" : "Confirm sync", exact: true }).click();
  await dialog.waitFor({ state: "hidden" });
}
