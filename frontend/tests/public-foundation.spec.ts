import { expect, test } from "@playwright/test";

test.beforeEach(async ({ page }) => {
  await page.route("**/api/v1/users/me", (route) => route.fulfill({ status: 401, contentType: "application/json", body: JSON.stringify({ detail: "Not authenticated" }) }));
  await page.goto("/");
});

test("public home keeps the approved navigation and story", async ({ page }) => {
  await expect(page.getByRole("heading", { name: "让多路训练视频，变成可复盘的篮球洞察" })).toBeVisible();
  await expect(page.getByRole("navigation", { name: "主导航" }).getByRole("link")).toHaveCount(2);
  await expect(page.getByTestId("capability-card")).toHaveCount(3);
  await expect(page.getByTestId("public-example-card")).toHaveCount(2);
  await expect(page.getByRole("link", { name: "GitHub" })).toHaveAttribute("href", "https://github.com/Siyuan-Xue/dashanbing-backend");
  await expect(page.getByRole("link", { name: "在线使用" })).toBeVisible();
});

test("responsive home never creates horizontal page overflow", async ({ page }) => {
  const dimensions = await page.evaluate(() => ({ viewport: window.innerWidth, page: document.documentElement.scrollWidth }));
  expect(dimensions.page).toBeLessThanOrEqual(dimensions.viewport);
});
