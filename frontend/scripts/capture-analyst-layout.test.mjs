// Synthetic layout fixtures only. These in-memory PNGs never become public assets.
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { chromium } from "@playwright/test";
import { captureClips } from "./capture-analyst-guard.mjs";

const css = (await Promise.all(["../src/styles.css", "../src/styles/workspace.css", "../src/styles/analyst.css"].map(path => readFile(new URL(path, import.meta.url), "utf8")))).join("\n").replace(/@import[^;]+;/g, "");
test("native browser crops keep all 16 fixture variants bounded at 2x and profile headers stay on one line", async () => {
  const browser = await chromium.launch();
  try {
    for (const locale of ["zh", "en"]) for (const theme of ["light", "dark"]) for (const viewport of ["desktop", "mobile"]) {
      const context = await browser.newContext({ viewport: { width: viewport === "desktop" ? 1440 : 390, height: 844 }, deviceScaleFactor: 2, colorScheme: theme });
      const page = await context.newPage();
      await page.setContent(`<style>${css}</style><div class="workspace-page"><div class="result-workspace"><div class="media-stage"></div><section class="result-insights-panel">Raw tabs stay outside both crops</section><section class="analyst-panel"><div class="analyst-header">${locale === "zh" ? "测试分析师" : "Fixture analyst"}</div><div class="analyst-columns"><section class="analyst-report"><h3>Fixture report</h3><p data-report-summary class="analyst-summary">${("Fixture only · " + (locale === "zh" ? "测试布局" : "Layout check") + "<br>").repeat(4)}</p>${"<p>Fixture detail</p>".repeat(40)}</section></div></section></div></div>`);
      // Keep the video width representative of the real desktop sidebar/content layout.
      await page.addStyleTag({ content: ".workspace-page { max-width: 1184px; margin: 0 auto; }" });
      const layout = await page.evaluate(() => {
        const box = selector => { const r = document.querySelector(selector).getBoundingClientRect(); return { x: r.x, y: r.y, width: r.width, height: r.height }; };
        const lines = selector => { const range = document.createRange(); range.selectNodeContents(document.querySelector(selector)); return [...range.getClientRects()].filter(r => r.height > 0).map(r => r.bottom); };
        return { video: box(".media-stage"), analyst: box(".analyst-panel"), raw: box(".result-insights-panel"), report: box(".analyst-report"), summaryLines: lines("[data-report-summary]"), textLines: lines(".analyst-report") };
      });
      for (const clip of Object.values(captureClips(layout, viewport))) {
        const png = await page.screenshot({ clip, fullPage: true, scale: "device" });
        assert.equal(png.readUInt32BE(16), clip.width * 2);
        assert.equal(png.readUInt32BE(20), clip.height * 2);
        assert.ok(clip.y + clip.height <= layout.raw.y + 1 || clip.y >= layout.raw.y + layout.raw.height - 1, JSON.stringify({ clip, raw: layout.raw }));
      }
      await context.close();
    }
    const page = await browser.newPage();
    for (const width of [320, 640]) for (const name of ["训练档案", "Training profiles"]) {
      await page.setViewportSize({ width, height: 844 });
      await page.setContent(`<style>${css}</style><div class="workspace-page profiles-page"><header class="detail-header"><div class="detail-heading"><h1>${name}</h1></div><button class="button button-primary button-icon" aria-label="New profile">+</button></header></div>`);
      const heading = await page.locator("h1").boundingBox(); const button = await page.locator("button").boundingBox();
      assert.ok(button.x >= heading.x + heading.width, `Title and action overlap at ${width}px`);
      assert.ok(Math.abs(heading.y + heading.height / 2 - button.y - button.height / 2) < 2, `Header wraps at ${width}px`);
      assert.ok(button.x + button.width <= width, `Action clips at ${width}px`);
    }
  } finally { await browser.close(); }
});
