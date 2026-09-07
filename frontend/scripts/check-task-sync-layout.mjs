// Component-only browser check. Every API/media response is synthetic; no backend is contacted.
import assert from "node:assert/strict";
import { fileURLToPath } from "node:url";
import { createServer } from "vite";
import { chromium } from "@playwright/test";

const root = fileURLToPath(new URL("../", import.meta.url));
const server = await createServer({ root, cacheDir: "/tmp/task-sync-vite-cache", server: { host: "127.0.0.1", port: 53174, strictPort: true }, configFile: false });
let browser;
const cameras = ["cam_01", "cam_02", "cam_03", "cam_04"];
const versions = { cam_01: "fixture-1", cam_02: "fixture-2", cam_03: "fixture-3", cam_04: "fixture-4" };
const selected = { cam_01: 120, cam_02: 80, cam_03: 40, cam_04: 160 };
const config = { schema_version: 1, anchor_camera: "cam_03", selected_timestamps_ms: selected,
  input_versions: versions, camera_time_offsets_ms: { cam_01: 80, cam_02: 40, cam_03: 0, cam_04: 120 },
  durations_ms: Object.fromEntries(cameras.map(camera => [camera, 400])), overlap_start_ms: 0, overlap_end_ms: 280, confirmed_at: "2026-09-07T01:00:00Z" };
const metadata = { status: "ready", source_versions: versions, error: null, cameras: Object.fromEntries(cameras.map(camera => [camera, {
  source_version: versions[camera], duration_ms: 400, fps: 25, frame_count: 10, source_start_pts_ms: 0,
  frame_timestamps_ms: [0, 40, 80, 120, 160, 200, 240, 280, 320, 360], video_url: `/api/v1/tasks/synthetic-sync/sync/preview/${camera}?source_version=${versions[camera]}`,
}])) };
try {
  await server.listen();
  const origin = server.resolvedUrls.local[0];
  browser = await chromium.launch({ headless: true });
  const page = await browser.newPage();
  const errors = [];
  page.on("pageerror", error => errors.push(error.message));
  let image = "", video = Buffer.alloc(0);
  await page.route("**/__sync_fixture", route => route.fulfill({ contentType: "text/html", body: '<!doctype html><html><head><meta name="viewport" content="width=device-width,initial-scale=1"/></head><body><div id="root"></div><script type="module" src="/src/test/TaskSyncHarness.tsx"></script></body></html>' }));
  await page.route("**/api/**", async route => {
    const url = new URL(route.request().url());
    if (url.pathname.endsWith("/sync")) return route.fulfill({ json: { status: "confirmed", source_versions: versions, config } });
    if (url.pathname.endsWith("/sync/preview")) return route.fulfill({ json: metadata });
    if (url.pathname.includes("/sync/preview/")) return route.fulfill({ contentType: "video/webm", body: video });
    if (url.pathname.includes("/sync/frames/")) {
      const camera = url.pathname.split("/").at(-1), time = Number(url.searchParams.get("time_ms"));
      return route.fulfill({ json: { camera, source_version: versions[camera], requested_time_ms: time, actual_time_ms: time, source_pts_ms: time, frame_index: time / 40, image_data_url: image } });
    }
    return route.abort();
  });
  await page.goto(`${origin}__sync_fixture`);
  await page.getByRole("button", { name: "Open fixture" }).waitFor();
  const media = await page.evaluate(async () => {
    const canvas = document.createElement("canvas"); canvas.width = 320; canvas.height = 180;
    const context = canvas.getContext("2d"); context.fillStyle = "#18485e"; context.fillRect(0, 0, 320, 180);
    context.fillStyle = "white"; context.font = "20px sans-serif"; context.fillText("SYNTHETIC TEST", 65, 96);
    const stream = canvas.captureStream(25), chunks = [];
    const recorder = new MediaRecorder(stream, { mimeType: "video/webm" });
    const recorded = new Promise(resolve => { recorder.ondataavailable = event => chunks.push(event.data); recorder.onstop = async () => resolve(Array.from(new Uint8Array(await new Blob(chunks).arrayBuffer()))); });
    recorder.start(); const redraw = setInterval(() => context.fillRect(0, 0, 1, 1), 40);
    await new Promise(resolve => setTimeout(resolve, 650)); clearInterval(redraw); recorder.stop();
    const bytes = await recorded; stream.getTracks().forEach(track => track.stop());
    return { image: canvas.toDataURL("image/jpeg"), bytes };
  });
  image = media.image; video = Buffer.from(media.bytes);
  for (const [width, height, locale] of [[1280, 900, "zh"], [320, 568, "zh"], [320, 568, "en"]]) {
    await page.setViewportSize({ width, height });
    await page.evaluate(value => localStorage.setItem("dashanbing-locale", value), locale);
    await page.reload(); await page.getByRole("button", { name: "Open fixture" }).click();
    const confirm = page.getByRole("button", { name: locale === "zh" ? "确认同步" : "Confirm sync" });
    await confirm.waitFor(); await page.waitForFunction(() => document.querySelectorAll(".video-sync-select:not(:disabled)").length === 4);
    const geometry = await page.evaluate(() => {
      const visible = [...document.querySelectorAll(".video-sync-camera")].filter(node => !node.hidden);
      const rect = node => { const box = node.getBoundingClientRect(); return { x: box.x, y: box.y, width: box.width, height: box.height, right: box.right, bottom: box.bottom }; };
      return {
        dialog: rect(document.querySelector(".video-sync-dialog")), panels: visible.map(rect), labels: visible.map(node => node.getAttribute("aria-label")),
        clippedControls: [...document.querySelectorAll(".video-sync-dialog button, .video-sync-dialog input")].filter(node => !node.closest("[hidden]")).map(rect).filter(box => box.x < 0 || box.right > innerWidth + .5 || box.y < 0 || box.bottom > innerHeight + .5),
        textOverflow: [...document.querySelectorAll(".video-sync-frame-controls button")].filter(node => !node.closest("[hidden]") && node.scrollWidth > node.clientWidth + 1).map(node => node.textContent),
        pageWidth: document.documentElement.scrollWidth,
      };
    });
    assert.equal(geometry.pageWidth, width, `${locale}/${width}: no horizontal page overflow`);
    assert.equal(geometry.clippedControls.length, 0, `${locale}/${width}: controls fit: ${JSON.stringify(geometry.clippedControls)}`);
    assert.deepEqual(geometry.textOverflow, [], `${locale}/${width}: control labels fit`);
    if (width === 320) {
      assert.equal(geometry.dialog.height, height); assert.equal(geometry.panels.length, 2);
      assert.match(geometry.labels[0], /3/); assert.ok(geometry.panels[0].y < geometry.panels[1].y);
    } else {
      assert.equal(geometry.panels.length, 4); assert.equal(geometry.panels[0].y, geometry.panels[1].y); assert.equal(geometry.panels[2].y, geometry.panels[3].y);
    }
    await page.screenshot({ path: `/tmp/task-sync-${width}-${locale}.png` });
    console.log(JSON.stringify({ width, height, locale, panels: geometry.panels.length, controlsFit: true }));
    await page.keyboard.press("Escape");
    assert.equal(await page.getByRole("button", { name: "Open fixture" }).evaluate(node => document.activeElement === node), true);
  }
  assert.deepEqual(errors, []);
  console.log("Synthetic component layout and focus checks passed. No backend integration or production media tested.");
} finally { await browser?.close(); await server.close(); }
