#!/usr/bin/env node
import { parseArgs } from "node:util";
import { fileURLToPath } from "node:url";
import { resolve, join, dirname } from "node:path";
import { mkdtemp, mkdir, readFile, writeFile, rename, rm, copyFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { spawnSync } from "node:child_process";
import { createHash } from "node:crypto";
import { chromium } from "@playwright/test";
import { assertVerifiedReport, captureClips, assertCaptureMatrix } from "./capture-analyst-guard.mjs";

const { values } = parseArgs({ options: {
  "base-url": { type: "string", default: "http://127.0.0.1:5173" },
  "storage-state": { type: "string" }, "output-dir": { type: "string" },
  python: { type: "string", default: process.env.PYTHON || "python3" },
  "wait-seconds": { type: "string", default: "0" }, help: { type: "boolean", default: false },
} });
if (values.help) {
  console.log("Usage: node scripts/capture-analyst.mjs --base-url http://localhost:5183 --storage-state /private/tmp/analyst-auth.json [--python /path/to/python3] [--wait-seconds 600]\nRequires Playwright Chromium, Python Pillow, and authenticated state for a real backend. Captures 16 native main/detail crops of quick-demo in desktop/mobile × light/dark × zh/en. No mocks, report generation, or provider API calls. See scripts/README-analyst.md.");
  process.exit(0);
}
if (!values["storage-state"]) throw new Error("--storage-state is required; use an authenticated Playwright storage state file");
const baseURL = new URL(values["base-url"]);
if (!["http:", "https:"].includes(baseURL.protocol) || baseURL.username || baseURL.password) throw new Error("Use an HTTP(S) origin without credentials in the URL");
const waitSeconds = Number(values["wait-seconds"]);
if (!Number.isFinite(waitSeconds) || waitSeconds < 0) throw new Error("--wait-seconds must be a nonnegative number");
const output = values["output-dir"] ? resolve(values["output-dir"]) : resolve(dirname(fileURLToPath(import.meta.url)), "../public/assets/previews/analyst");
const storageState = JSON.parse(await readFile(resolve(values["storage-state"]), "utf8"));
const python = (code, input) => {
  const result = spawnSync(values.python, ["-c", code], { input, maxBuffer: 64 * 1024 * 1024 });
  if (result.error || result.status !== 0) throw new Error(`Python capture helper failed: ${result.error?.message || result.stderr.toString().slice(0, 800)}`);
  return result;
};
python("from PIL import Image, features; assert features.check('webp'), 'Pillow WebP support is required'", "");
// Match the backend's Python canonical JSON exactly, including float serialization
const factsDigest = raw => python("import json,hashlib,sys; facts=json.load(sys.stdin)['facts']; print(hashlib.sha256(json.dumps(facts,ensure_ascii=False,sort_keys=True,separators=(',',':'),default=str).encode()).hexdigest())", raw).stdout.toString().trim();
const reportDigest = raw => python("import json,hashlib,sys; report=json.load(sys.stdin)['report']; print(hashlib.sha256(json.dumps(report,ensure_ascii=False,sort_keys=True,separators=(',',':'),default=str).encode()).hexdigest())", raw).stdout.toString().trim();
const browser = await chromium.launch();
const staging = await mkdtemp(join(tmpdir(), "analyst-capture-"));
const images = []; const capturedAt = new Date().toISOString();
try {
  for (const locale of ["zh", "en"]) for (const theme of ["light", "dark"]) for (const viewport of ["desktop", "mobile"]) {
    const context = await browser.newContext({ baseURL: baseURL.origin, storageState, serviceWorkers: "block", colorScheme: theme, locale: locale === "zh" ? "zh-CN" : "en-US", viewport: viewport === "desktop" ? { width: 1440, height: 1000 } : { width: 390, height: 844 }, deviceScaleFactor: 2, isMobile: viewport === "mobile", hasTouch: viewport === "mobile", reducedMotion: "reduce" });
    try {
      const identity = await context.request.get("/api/v1/users/me");
      const user = identity.ok() ? await identity.json() : null;
      if (!Number.isInteger(user?.id) || user.is_active !== true) throw new Error("Refusing capture: live backend did not authenticate the supplied cookie session");
      const endpoint = `/api/v1/presets/quick-demo/analyst/report?locale=${locale}&style=coach`;
      let state; let factsHash; let report; let reportHash;
      const deadline = Date.now() + waitSeconds * 1000;
      while (true) {
        const response = await context.request.get(endpoint);
        if (!response.ok()) throw new Error(`Preset report request failed (${response.status()})`);
        const raw = await response.text(); state = JSON.parse(raw); factsHash = factsDigest(raw);
        try { report = assertVerifiedReport(state, locale, factsHash); reportHash = reportDigest(raw); break; }
        catch (error) { if (Date.now() >= deadline) throw error; await new Promise(resolve => setTimeout(resolve, 5000)); }
      }
      const page = await context.newPage();
      // Fail closed if a future UI change attempts generation or chat while capturing.
      await page.route("**/api/v1/**", route => route.request().method() === "GET" ? route.continue() : route.abort());
      const errors = []; const forbidden = [];
      page.on("pageerror", error => errors.push(error.message));
      page.on("request", request => { if (/\/analyst\//.test(request.url()) && request.method() !== "GET") forbidden.push(request.method()); });
      await page.addInitScript(({ locale, theme }) => { localStorage.setItem("dashanbing-locale", locale); localStorage.setItem("dashanbing-theme", theme); sessionStorage.clear(); }, { locale, theme });
      const uiResponse = page.waitForResponse(response => new URL(response.url()).pathname === "/api/v1/presets/quick-demo/analyst/report" && new URL(response.url()).searchParams.get("locale") === locale);
      await page.goto("/workspace/examples/quick-demo#analyst", { waitUntil: "domcontentloaded" });
      const response = await uiResponse;
      const raw = await response.text(); const uiState = JSON.parse(raw);
      const uiReport = assertVerifiedReport(uiState, locale, factsDigest(raw));
      if (uiReport.id !== report.id || uiState.provenance.facts_hash !== factsHash || reportDigest(raw) !== reportHash) throw new Error("Report changed during capture; retry against a stable verified report");
      await page.locator('#analyst [data-report-status="completed"]').waitFor();
      const reportElement = page.locator("#analyst .analyst-report");
      if (await reportElement.getAttribute("data-report-id") !== report.id || await reportElement.getAttribute("data-report-model") !== report.model || await reportElement.locator("[data-report-summary]").textContent() !== report.summary) throw new Error("Refusing capture: rendered UI differs from the verified report");
      await page.waitForFunction(() => { const video = document.querySelector(".result-media-panel video"); return video instanceof HTMLVideoElement && video.readyState >= 2 && !video.error; });
      await page.locator(".result-media-panel video").evaluate(async video => {
        video.pause();
        const time = Math.min(6, Math.max(0, video.duration - .1));
        if (Math.abs(video.currentTime - time) > .01) await new Promise(resolve => { video.addEventListener("seeked", resolve, { once: true }); video.currentTime = time; });
      });
      await page.evaluate(() => document.fonts.ready);
      if (errors.length || forbidden.length) throw new Error("Refusing capture: page errors or AI write requests occurred");
      await page.evaluate(() => window.scrollTo(0, 0));
      const layout = await page.evaluate(() => {
        const box = selector => {
          const element = document.querySelector(selector);
          if (!element) throw new Error(`Missing capture element: ${selector}`);
          const rect = element.getBoundingClientRect();
          return { x: rect.x + scrollX, y: rect.y + scrollY, width: rect.width, height: rect.height };
        };
        const lines = selector => {
          const element = document.querySelector(selector);
          const walker = document.createTreeWalker(element, NodeFilter.SHOW_TEXT);
          const bottoms = []; let node;
          while ((node = walker.nextNode())) {
            if (!node.textContent.trim()) continue;
            const range = document.createRange(); range.selectNodeContents(node);
            for (const rect of range.getClientRects()) if (rect.height && rect.width) bottoms.push(rect.bottom + scrollY);
          }
          return [...new Set(bottoms)].sort((a, b) => a - b);
        };
        return { video: box(".media-stage"), analyst: box("#analyst"), report: box("#analyst .analyst-report"), raw: box(".result-insights-panel"), composer: box(".analyst-composer"), summaryLines: lines("[data-report-summary]"), textLines: lines("#analyst .analyst-report") };
      });
      const clips = captureClips(layout, viewport);
      for (const kind of ["main", "analyst"]) {
        const png = await page.screenshot({ type: "png", clip: clips[kind], fullPage: true, animations: "disabled", scale: "device" });
        const converted = python("from PIL import Image; import io,json,sys; image=Image.open(io.BytesIO(sys.stdin.buffer.read())); print(json.dumps({'width':image.width,'height':image.height}),file=sys.stderr); image.save(sys.stdout.buffer,format='WEBP',quality=88,method=6)", png);
        const dimensions = JSON.parse(converted.stderr.toString());
        if (dimensions.width !== clips[kind].width * 2 || dimensions.height !== clips[kind].height * 2) throw new Error("Refusing capture: native retina dimensions do not match the crop");
        const hash = createHash("sha256").update(converted.stdout).digest("hex").slice(0, 12);
        const name = `${locale}-${theme}-${viewport}-${kind}-${hash}.webp`;
        await writeFile(join(staging, name), converted.stdout);
        images.push({ locale, theme, viewport, kind, src: `/assets/previews/analyst/${name}`, ...dimensions, pixel_ratio: 2, report_id: report.id, report_hash: reportHash, model: report.model, facts_hash: factsHash });
        console.log(`Verified ${locale}/${theme}/${viewport}/${kind}: ${dimensions.width}×${dimensions.height}`);
      }
    } finally { await context.close(); }
  }
  assertCaptureMatrix(images);
  const manifest = { version: 2, source: { kind: "preset", id: "quick-demo", href: "/workspace/examples/quick-demo#analyst" }, captured_at: capturedAt, verification: { provider: "glm", verified: true }, images };
  // Publish the manifest last; partial failures never switch the homepage to incomplete captures
  await mkdir(output, { recursive: true });
  for (const image of images) await copyFile(join(staging, image.src.split("/").at(-1)), join(output, image.src.split("/").at(-1)));
  const temporaryManifest = join(output, `.manifest-${Date.now()}.tmp`);
  await writeFile(temporaryManifest, JSON.stringify(manifest, null, 2) + "\n");
  await rename(temporaryManifest, join(output, "manifest.json"));
  console.log(`Wrote 16 verified static WebP images and ${join(output, "manifest.json")}`);
} finally { await browser.close(); await rm(staging, { recursive: true, force: true }); }
