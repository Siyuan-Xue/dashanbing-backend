#!/usr/bin/env node
/**
 * Real, isolated HTTP UI evidence collector. Does not start servers, build assets,
 * seed data, mock responses, run repairs, or optimize/retry failed cases.
 * Relative paths resolve from the repository root. Default mode is dry-run.
 *
 * node frontend/scripts/capture-closeout.mjs --output-dir runtime/release-closeout/ui-plan
 * node frontend/scripts/capture-closeout.mjs --mode smoke --output-dir runtime/release-closeout/ui-smoke-001
 * Full measurement is opt-in: --mode capture (300 page cases + role boundaries).
 */
import { parseArgs, promisify } from "node:util";
import { execFile } from "node:child_process";
import { resolve, join, dirname, relative, isAbsolute } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";
import { mkdir, readFile, writeFile, appendFile, realpath, lstat } from "node:fs/promises";

const ROOT = fileURLToPath(new URL("../../", import.meta.url));
const RUNTIME = join(ROOT, "runtime");
const FIXTURE_ORIGIN = "http://127.0.0.1:8013";
const PAGES = [
  { page: "home", path: "/", role: "anonymous" },
  { page: "login", path: "/login", role: "anonymous" },
  { page: "register", path: "/register", role: "anonymous" },
  { page: "new", path: "/workspace/new", role: "user" },
  { page: "tasks", path: "/workspace/tasks", role: "user" },
  { page: "profiles", path: "/workspace/profiles", role: "user" },
  { page: "settings", path: "/workspace/settings", role: "user" },
  { page: "api/docs", path: "/api/docs", role: "user" },
  { page: "api/keys", path: "/api/keys", role: "user" },
  ...["overview", "users", "scheduling", "quotas", "operations", "audit"].map(section => ({ page: `admin-${section}`, path: `/admin/${section}`, role: "admin" })),
];
const inside = (path, root) => { const part = relative(root, path); return part !== "" && !part.startsWith(`..`) && !isAbsolute(part); };
function choiceList(raw, allowed, label) {
  const items = raw.split(",");
  if (!items.length || new Set(items).size !== items.length || items.some(item => !allowed.includes(item))) throw new Error(`Invalid ${label}`);
  return items;
}
export function parseOptions(argv) {
  const { values } = parseArgs({ args: argv, strict: true, options: {
    mode: { type: "string", default: "dry-run" }, "output-dir": { type: "string" },
    "base-url": { type: "string", default: FIXTURE_ORIGIN },
    credentials: { type: "string", default: "runtime/release-closeout/fixture-credentials.json" },
    sizes: { type: "string", default: "320x900,390x900,768x900,1440x900,1920x900" },
    locales: { type: "string", default: "zh,en" }, themes: { type: "string", default: "light,dark" },
    pages: { type: "string" }, "executable-path": { type: "string" }, browser: { type: "string", default: "auto" },
    "timeout-ms": { type: "string", default: "20000" }, "settle-ms": { type: "string", default: "350" },
    "full-page": { type: "boolean", default: false }, help: { type: "boolean", default: false },
  } });
  if (values.help) return { help: true };
  if (!values["output-dir"]) throw new Error("An explicit --output-dir inside the ignored runtime directory is required");
  const output = resolve(ROOT, values["output-dir"]);
  if (!inside(output, RUNTIME)) throw new Error("Evidence must be a new subdirectory inside ignored runtime");
  let base;
  try { base = new URL(values["base-url"]); } catch { throw new Error("Invalid local fixture origin"); }
  if (base.origin !== FIXTURE_ORIGIN || base.username || base.password || base.pathname !== "/" || base.search || base.hash) throw new Error("Only the isolated http://127.0.0.1:8013 fixture origin is supported");
  const credentials = resolve(ROOT, values.credentials);
  if (!inside(credentials, RUNTIME)) throw new Error("Credentials must come from an isolated runtime fixture");
  if (!["dry-run", "smoke", "capture"].includes(values.mode)) throw new Error("Mode must be dry-run, smoke, or capture");
  if (!["auto", "chrome", "chromium"].includes(values.browser)) throw new Error("Browser must be auto, chrome, or chromium");
  const sizes = values.sizes.split(",").map(value => {
    const match = /^(\d+)x(\d+)$/.exec(value);
    const width = Number(match?.[1]), height = Number(match?.[2]);
    if (!match || width < 320 || width > 3840 || height < 320 || height > 2160) throw new Error("Use exact WIDTHxHEIGHT sizes within 320..3840 by 320..2160");
    return { width, height };
  });
  if (new Set(sizes.map(size => `${size.width}x${size.height}`)).size !== sizes.length) throw new Error("Duplicate sizes are not allowed");
  const timeout = Number(values["timeout-ms"]), settle = Number(values["settle-ms"]);
  if (!Number.isInteger(timeout) || timeout < 1000 || timeout > 60000 || !Number.isInteger(settle) || settle < 0 || settle > 5000) throw new Error("Invalid timeout or settling window");
  return { mode: values.mode, output, credentials, base: base.origin, sizes,
    locales: choiceList(values.locales, ["zh", "en"], "locales"), themes: choiceList(values.themes, ["light", "dark"], "themes"),
    pages: values.pages ? choiceList(values.pages, PAGES.map(page => page.page), "pages") : null,
    browser: values.browser, executablePath: values["executable-path"] ? resolve(values["executable-path"]) : null, timeout, settle, fullPage: values["full-page"] };
}
export function buildPlan(options) {
  const variants = options.sizes.flatMap(viewport => options.locales.flatMap(locale => options.themes.map(theme => ({ viewport, screen: { ...viewport }, deviceScaleFactor: 1, locale, theme }))));
  const pages = PAGES.filter(page => !options.pages || options.pages.includes(page.page));
  let cases = variants.flatMap(variant => pages.map(page => ({ ...variant, ...page })));
  if (options.mode === "smoke") {
    const defaults = ["home", "login", "new", "admin-overview"];
    const selected = options.pages ? pages.slice(0, 4) : defaults.map(name => PAGES.find(page => page.page === name));
    cases = selected.map((page, index) => {
      const viewport = index === 0 ? options.sizes[0] : index === 1 ? (options.sizes[1] || options.sizes[0]) : (options.sizes.find(size => size.width === 1440) || options.sizes.at(-1));
      return { ...page, viewport, screen: { ...viewport }, deviceScaleFactor: 1, locale: index === 0 ? options.locales[0] : options.locales.at(-1), theme: index === 3 ? options.themes.at(-1) : options.themes[0] };
    });
  }
  cases = cases.map(item => ({ ...item, id: `${item.page.replaceAll("/", "-")}-${item.role}-${item.viewport.width}x${item.viewport.height}-${item.locale}-${item.theme}` }));
  return { schema_version: 1, scope: options.mode === "smoke" ? "development_smoke_not_acceptance" : options.mode === "dry-run" ? "dry_run_no_measurements" : "local_fixture_ui_measurements", mode: options.mode,
    base_url: options.base, evidence_dir: options.output, cases,
    boundary_variants: options.mode === "smoke" ? [variants.find(item => item.viewport.width === 390 && item.locale === "en" && item.theme === "light") || variants[0]] : variants,
    measurement_policy: "Fresh context per page; authenticated pages measured after real UI login. Playwright request routing disables the HTTP cache. One attempt per case. Bounded current main-document API-read quiet window before capture, no full network-idle claim. Previous-document reads remain unresolved evidence unless a browser terminal event arrives. No acceptance thresholds for speed.",
    screenshot_policy: "Viewport PNG at deviceScaleFactor=1; exact dimensions verified from PNG header. Geometry stored separately. Optional full-page PNG is separately identified. Credential fields and fixture identities masked.",
    network_policy: "Only this fixture origin. Read requests plus UI login/logout only. No mocked responses. No traces, HAR, storage state, headers, request/response bodies, or credential output.",
  };
}
export function makeRedactor(credentials = {}) {
  const secrets = new Set();
  function collect(value, key = "") {
    if (typeof value === "string" && /password|token|secret|username|email/i.test(key) && value) { secrets.add(value); secrets.add(encodeURIComponent(value)); secrets.add(new URLSearchParams({ x: value }).toString().slice(2)); }
    else if (Array.isArray(value)) value.forEach(item => collect(item));
    else if (value && typeof value === "object") Object.entries(value).forEach(([key, item]) => collect(item, key));
  }
  collect(credentials);
  const ordered = [...secrets].sort((a, b) => b.length - a.length);
  const clean = text => {
    for (const secret of ordered) text = text.split(secret).join("[REDACTED]");
    return text.replace(/\bBearer\s+[^\s"',;]+/gi, "Bearer [REDACTED]")
      .replace(/\b(?:set-cookie|cookie)\s*:[^\r\n]*/gi, "Cookie: [REDACTED]")
      .replace(/\b(access_token|refresh_token|password|jwt_secret|authorization)\s*[=:]\s*[^\s"',;&]+/gi, "$1=[REDACTED]")
      .replace(/\beyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\b/g, "[REDACTED]");
  };
  const redact = value => typeof value === "string" ? clean(value) : Array.isArray(value) ? value.map(redact) : value && typeof value === "object" ? Object.fromEntries(Object.entries(value).map(([key, item]) => [key, /^(?:password|access_token|refresh_token|jwt_secret|authorization|cookie)$/i.test(key) ? "[REDACTED]" : redact(item)])) : value;
  return redact;
}
export function inspectGeometry(value) {
  return { horizontalOverflowPx: Math.max(0, value.document.scrollWidth - value.viewport.width),
    exactViewport: value.viewport.width === value.requested.width && value.viewport.height === value.requested.height,
    exactScreen: value.screen.width === value.requested.width && value.screen.height === value.requested.height,
    exactViewportScreenshot: value.screenshot?.width === value.requested.width && value.screenshot?.height === value.requested.height };
}
export async function openPublicAccount(page) {
  const account = page.locator(".account-link");
  await account.waitFor({ state: "attached" });
  if (!await account.isVisible()) {
    const menu = page.locator(".public-menu-toggle");
    await menu.waitFor({ state: "visible" });
    if (await menu.getAttribute("aria-expanded") !== "true") await menu.click();
  }
  await account.waitFor({ state: "visible" });
  if (await account.getAttribute("aria-expanded") !== "true") await account.click();
  await page.locator("#account-dropdown").waitFor({ state: "visible" });
}
export function isExpectedBootstrap401(response, base) {
  return response.event === "response" && response.method === "GET" && response.url === `${base}/api/v1/users/me`
    && response.status === 401 && response.authenticated_at_start === false;
}
export function classifyConsoleEvents(consoleEvents, network, base) {
  const expected = network.filter(response => isExpectedBootstrap401(response, base)), used = new Set();
  return consoleEvents.map(entry => {
    if (entry.type !== "error") return { ...entry, classification: "console" };
    const index = /^Failed to load resource: the server responded with a status of 401(?:\s|\(|$)/.test(entry.text)
      ? expected.findIndex((response, index) => !used.has(index) && entry.location?.url === response.url && Math.abs(entry.at_ms - response.at_ms) <= 2000) : -1;
    if (index < 0) return { ...entry, classification: "unexpected_error" };
    used.add(index);
    return { ...entry, classification: "expected_account_bootstrap_401", correlated_response_at_ms: expected[index].at_ms };
  });
}
export function createApiReadTracker(base, now = () => performance.now()) {
  // CDP request IDs survive navigation and redirects. Response headers alone do
  // not end a read; only browser loadingFinished/loadingFailed events do.
  const pending = new Map(), superseded = new Map(), activeLoaders = new Map(), retiredLoaders = new Set();
  const loaderKey = (frame, loader) => `${frame}:${loader}`;
  const retire = (entry, replacement) => {
    const archived = { ...entry, terminal: null, classification: "superseded_main_document_unresolved", replacement_loader_id: replacement, superseded_at_ms: now() };
    pending.delete(entry.request_id); superseded.set(entry.request_id, archived);
    return { ...archived };
  };
  return {
    source: "CDP.Network + Page.frameNavigated",
    get size() { return pending.size; },
    navigate(frame) {
      if (frame.parentId || !frame.id || !frame.loaderId) return [];
      const previous = activeLoaders.get(frame.id);
      if (previous && previous !== frame.loaderId) retiredLoaders.add(loaderKey(frame.id, previous));
      activeLoaders.set(frame.id, frame.loaderId);
      const archived = [];
      for (const entry of pending.values()) {
        if (entry.frame_id === frame.id && entry.loader_id && entry.loader_id !== frame.loaderId) {
          retiredLoaders.add(loaderKey(frame.id, entry.loader_id));
          archived.push(retire(entry, frame.loaderId));
        }
      }
      return archived;
    },
    start(data) {
      const redirected = pending.get(data.requestId) || superseded.get(data.requestId);
      pending.delete(data.requestId); // A redirect reuses the browser request ID.
      superseded.delete(data.requestId);
      const url = new URL(data.request.url);
      if (data.request.method !== "GET" || url.origin !== base || !url.pathname.startsWith("/api/v1/")) return redirected ? { ...redirected, terminal: "redirect_outside_api", redirect_url: safeUrl(url.href) } : null;
      const entry = { request_id: data.requestId, loader_id: data.loaderId, frame_id: data.frameId, url: safeUrl(url.href), started_ms: now(), browser_timestamp: data.timestamp, response_status: null };
      if (retiredLoaders.has(loaderKey(data.frameId, data.loaderId))) return retire(entry, activeLoaders.get(data.frameId));
      pending.set(data.requestId, entry);
      return { ...entry };
    },
    response(data) {
      const entry = pending.get(data.requestId) || superseded.get(data.requestId);
      if (!entry) return null;
      entry.response_status = data.response.status;
      return { ...entry };
    },
    end(data, terminal) {
      const entry = pending.get(data.requestId) || superseded.get(data.requestId);
      if (!entry) return null;
      pending.delete(data.requestId);
      superseded.delete(data.requestId);
      return { ...entry, terminal, canceled: data.canceled ?? false, error: data.errorText ?? null, elapsed_ms: now() - entry.started_ms };
    },
    snapshot() { return [...pending.values()].map(entry => ({ ...entry, age_ms: now() - entry.started_ms })); },
    supersededSnapshot() { return [...superseded.values()].map(entry => ({ ...entry, age_ms: now() - entry.started_ms })); },
  };
}
export async function waitForReadQuiet(pending, { quietMs, timeoutMs, now = () => performance.now(), sleep = ms => new Promise(resolve => setTimeout(resolve, ms)) }) {
  const start = now(); let quietSince = pending.size ? null : start;
  const result = complete => ({ complete, elapsed_ms: now() - start, pending_count: pending.size,
    ...(pending.snapshot ? { evidence_source: pending.source, scope: "current_main_document_api_reads", pending_reads: pending.snapshot(), superseded_document_reads: pending.supersededSnapshot() } : {}) });
  while (now() - start < timeoutMs) {
    if (pending.size) quietSince = null;
    else { quietSince ??= now(); if (now() - quietSince >= quietMs) return result(true); }
    await sleep(Math.min(25, Math.max(1, quietMs || 1)));
  }
  return result(false);
}
export async function captureCases(cases, capture, record) {
  const results = [];
  for (const item of cases) {
    let result;
    try { result = await capture(item); }
    catch (error) { result = { id: item.id, status: "failed", stage: "case", error: error instanceof Error ? error.message : "Unknown failure" }; }
    results.push(result);
    await record(result);
  }
  return results;
}
export async function assertOutputDirectory(output, runtime = RUNTIME) {
  output = resolve(output); runtime = resolve(runtime);
  if (!inside(output, runtime)) throw new Error("Evidence must be below runtime");
  try { await lstat(output); throw new Error("Output already exists; choose a new evidence directory"); } catch (error) { if (error.code !== "ENOENT") throw error; }
  let ancestor = dirname(output);
  while (true) { try { await lstat(ancestor); break; } catch (error) { if (error.code !== "ENOENT") throw error; ancestor = dirname(ancestor); } }
  const realRuntime = await realpath(runtime), realAncestor = await realpath(ancestor);
  if (realAncestor !== realRuntime && !inside(realAncestor, realRuntime)) throw new Error("Evidence directory escapes runtime through a symlink");
}
const safeUrl = value => { try { const url = new URL(value); return url.origin + url.pathname + (url.search ? "?[query omitted]" : ""); } catch { return "[invalid URL]"; } };
const errorMessage = error => error instanceof Error ? error.message : "Unknown failure";
function pngSize(buffer) {
  if (buffer.length < 24 || buffer.subarray(0, 8).toString("hex") !== "89504e470d0a1a0a") throw new Error("Screenshot is not a PNG");
  return { width: buffer.readUInt32BE(16), height: buffer.readUInt32BE(20) };
}
async function readFixture(path) {
  let value;
  try { value = JSON.parse(await readFile(path, "utf8")); } catch { throw new Error("Could not read the fixture credentials JSON"); }
  const valid = item => item && typeof item.username === "string" && item.username && typeof item.password === "string" && item.password;
  if (value.fixture !== true || !valid(value.admin) || !valid(value.accounts?.[0])) throw new Error("Expected isolated fixture credentials with admin and accounts[0]");
  return value;
}
export function browserIdentity(versionOutput, executablePath) {
  const name = /^Google Chrome(?: for Testing)? /m.test(versionOutput) ? "Google Chrome" : /^Chromium /m.test(versionOutput) ? "Chromium" : "Unverified Chromium-family executable";
  return { name, executable_path: executablePath, executable_version: versionOutput.trim() };
}
async function launchBrowser(options) {
  const preference = options.browser;
  const { chromium } = await import("@playwright/test");
  if (options.executablePath) {
    const { stdout } = await promisify(execFile)(options.executablePath, ["--version"], { timeout: 5000, maxBuffer: 4096 });
    const browser = await chromium.launch({ headless: true, executablePath: options.executablePath });
    return { browser, info: { ...browserIdentity(stdout, options.executablePath), launch_channel: "explicit executable", version: browser.version(), fallback: false } };
  }
  if (preference !== "chromium") {
    try { const browser = await chromium.launch({ headless: true, channel: "chrome" }); return { browser, info: { name: "Google Chrome", launch_channel: "chrome", version: browser.version(), fallback: false } }; }
    catch { /* A Chromium user agent containing Chrome does not prove branded Chrome. */ }
  }
  const browser = await chromium.launch({ headless: true });
  return { browser, info: { name: "Chromium", launch_channel: "bundled chromium", version: browser.version(), fallback: preference !== "chromium", fallback_reason: preference !== "chromium" ? "Google Chrome launch unavailable" : null } };
}
async function createSession(browser, variant, options, redact) {
  const context = await browser.newContext({ viewport: variant.viewport, screen: variant.screen, deviceScaleFactor: 1, locale: variant.locale === "zh" ? "zh-CN" : "en-US", colorScheme: variant.theme, reducedMotion: "reduce", serviceWorkers: "block", acceptDownloads: false });
  const page = await context.newPage();
  page.setDefaultTimeout(options.timeout); page.setDefaultNavigationTimeout(options.timeout);
  const pendingReads = createApiReadTracker(options.base), auth = { authenticated: false }, requestAuth = new WeakMap();
  const started = performance.now(), phase = { value: "setup" }, events = { console: [], page_errors: [], network: [], api_reads: [], document_transitions: [], blocked_requests: [], dialogs: [] };
  const event = data => redact({ at_ms: performance.now() - started, phase: phase.value, ...data });
  // Only a browser-confirmed main-document replacement retires old-loader reads
  // from render readiness. Keep them as unresolved evidence, never invent an end.
  // Current/unknown-loader reads never expire by age; they still cause timeouts.
  const cdp = await context.newCDPSession(page);
  const recordRead = (kind, data) => { if (data) events.api_reads.push(event({ event: kind, ...data })); };
  cdp.on("Network.requestWillBeSent", data => recordRead("requestWillBeSent", pendingReads.start(data)));
  cdp.on("Network.responseReceived", data => recordRead("responseReceived", pendingReads.response(data)));
  for (const terminal of ["loadingFinished", "loadingFailed"]) cdp.on(`Network.${terminal}`, data => recordRead(terminal, pendingReads.end(data, terminal)));
  cdp.on("Page.frameNavigated", ({ frame }) => {
    if (frame.parentId) return;
    const archived = pendingReads.navigate(frame);
    events.document_transitions.push(event({ event: "Page.frameNavigated", frame_id: frame.id, loader_id: frame.loaderId, url: safeUrl(frame.url), superseded_reads: archived }));
  });
  await cdp.send("Page.enable");
  await cdp.send("Network.enable");
  page.on("request", request => requestAuth.set(request, auth.authenticated));
  page.on("console", message => { const location = message.location(); events.console.push(event({ type: message.type(), text: message.text(), location: { ...location, url: safeUrl(location.url) } })); });
  page.on("pageerror", error => events.page_errors.push(event({ message: error.message, stack: error.stack })));
  page.on("response", response => {
    const request = response.request(), url = new URL(response.url());
    const data = { event: "response", method: request.method(), url: safeUrl(response.url()), status: response.status(), resource_type: request.resourceType(), authenticated_at_start: requestAuth.get(request) };
    if (isExpectedBootstrap401(data, options.base)) data.classification = "expected_account_bootstrap_401";
    events.network.push(event(data));
    if (url.origin === options.base && request.method() === "POST" && response.ok()) {
      if (url.pathname === "/api/v1/login/access-token") auth.authenticated = true;
      if (url.pathname === "/api/v1/logout") auth.authenticated = false;
    }
  });
  page.on("requestfinished", request => events.network.push(event({ event: "finished", method: request.method(), url: safeUrl(request.url()), resource_type: request.resourceType(), timing: request.timing() })));
  page.on("requestfailed", request => events.network.push(event({ event: "failed", method: request.method(), url: safeUrl(request.url()), failure: request.failure()?.errorText })));
  page.on("dialog", dialog => { events.dialogs.push(event({ type: dialog.type(), message: dialog.message() })); void dialog.dismiss(); });
  await context.route("**/*", async route => {
    const request = route.request(), url = new URL(request.url());
    const read = ["GET", "HEAD", "OPTIONS"].includes(request.method());
    const auth = request.method() === "POST" && ["/api/v1/login/access-token", "/api/v1/logout"].includes(url.pathname);
    if (url.origin === options.base && (read || auth)) return route.continue();
    events.blocked_requests.push(event({ method: request.method(), url: safeUrl(url.href), reason: url.origin !== options.base ? "outside_fixture_origin" : "mutation_outside_login_logout" }));
    return route.abort("blockedbyclient");
  });
  await page.addInitScript(({ locale, theme }) => {
    localStorage.setItem("dashanbing-locale", locale); localStorage.setItem("dashanbing-theme", theme);
    globalThis.__closeoutPerformance = { longtasks: [], largest_contentful_paint: [] };
    for (const [type, target] of [["longtask", "longtasks"], ["largest-contentful-paint", "largest_contentful_paint"]]) {
      try { new PerformanceObserver(list => list.getEntries().forEach(entry => globalThis.__closeoutPerformance[target].push({ startTime: entry.startTime, duration: entry.duration, size: entry.size ?? null }))).observe({ type, buffered: true }); } catch { /* Unsupported observer is recorded below by supportedEntryTypes. */ }
    }
  }, { locale: variant.locale, theme: variant.theme });
  return { context, page, phase, events, pendingReads, auth };
}
async function signIn(session, role, credentials, options, next) {
  session.phase.value = "authentication";
  const credential = role === "admin" ? credentials.admin : credentials.accounts[0];
  await session.page.goto(`${options.base}/login?${new URLSearchParams({ next: next || (role === "admin" ? "/admin" : "/workspace/tasks") })}`, { waitUntil: "domcontentloaded" });
  await session.page.locator('input[name="identity"]').fill(credential.username);
  await session.page.locator('input[name="password"]').fill(credential.password);
  await session.page.locator('.auth-card button[type="submit"], .auth-card .auth-submit').click();
  await session.page.waitForURL(url => role === "admin" ? url.pathname === "/admin/overview" : url.pathname.startsWith("/workspace/"));
  const response = await session.context.request.get(`${options.base}/api/v1/users/me`);
  if (response.status() !== 200 || (await response.json()).role !== role) throw new Error("Fixture login did not establish the expected role");
  session.auth.authenticated = true;
  return { role, http_status: response.status(), landed_path: new URL(session.page.url()).pathname };
}
async function measureGeometry(page, requested) {
  return page.evaluate(requested => {
    const rect = element => { const box = element.getBoundingClientRect(); return { x: box.x, y: box.y, width: box.width, height: box.height, right: box.right, bottom: box.bottom }; };
    const visible = element => { const box = element.getBoundingClientRect(), style = getComputedStyle(element); return box.width > 0 && box.height > 0 && style.visibility !== "hidden" && style.display !== "none" && !element.closest('[hidden], [aria-hidden="true"], [inert]'); };
    const descriptor = element => ({ tag: element.tagName.toLowerCase(), classes: typeof element.className === "string" ? element.className : "", rect: rect(element) });
    return {
      requested, viewport: { width: innerWidth, height: innerHeight }, window: { outerWidth, outerHeight, devicePixelRatio },
      screen: { width: screen.width, height: screen.height, availWidth: screen.availWidth, availHeight: screen.availHeight, colorDepth: screen.colorDepth },
      visualViewport: visualViewport ? { width: visualViewport.width, height: visualViewport.height, scale: visualViewport.scale, offsetLeft: visualViewport.offsetLeft, offsetTop: visualViewport.offsetTop } : null,
      document: { clientWidth: document.documentElement.clientWidth, clientHeight: document.documentElement.clientHeight, scrollWidth: document.documentElement.scrollWidth, scrollHeight: document.documentElement.scrollHeight, bodyScrollWidth: document.body?.scrollWidth, bodyScrollHeight: document.body?.scrollHeight },
      effective_locale: document.documentElement.lang, effective_theme: document.documentElement.dataset.theme,
      overflow_elements: [...document.querySelectorAll("body *")].filter(visible).filter(element => { const box = element.getBoundingClientRect(); return box.right > innerWidth + 1 || box.left < -1; }).slice(0, 100).map(descriptor),
      contained_horizontal_scrollers: [...document.querySelectorAll("main *")].filter(visible).filter(element => ["auto", "scroll"].includes(getComputedStyle(element).overflowX) && element.scrollWidth > element.clientWidth + 1).slice(0, 30).map(element => ({ ...descriptor(element), clientWidth: element.clientWidth, scrollWidth: element.scrollWidth })),
      landmarks: [".public-header", ".workspace-sidebar", ".workspace-main", ".admin-page", ".admin-table", ".task-table", "main h1"].flatMap(selector => [...document.querySelectorAll(selector)].filter(visible).map(element => ({ selector, rect: rect(element) }))),
      table_headers: [...document.querySelectorAll("main table thead tr")].filter(visible).map(descriptor),
      table_rows: [...document.querySelectorAll("main table tbody tr")].filter(visible).slice(0, 30).map(descriptor),
    };
  }, requested);
}
async function timingSnapshot(page) {
  return page.evaluate(() => ({
    navigation: performance.getEntriesByType("navigation").map(entry => entry.toJSON()),
    paints: performance.getEntriesByType("paint").map(entry => entry.toJSON()),
    resources: performance.getEntriesByType("resource").map(entry => entry.toJSON()),
    observers: globalThis.__closeoutPerformance || null,
    supported_observers: PerformanceObserver.supportedEntryTypes,
    document_ready_state: document.readyState, at_ms: performance.now(),
  }));
}
function masks(page, credentials) {
  return [page.locator('input[type="password"], input[name="identity"], input[name="username"], input[name="email"], .account-info, .admin-account-identity strong, .api-secret'),
    ...[credentials.admin, credentials.accounts[0]].map(account => page.getByText(account.username, { exact: true }))];
}
async function collectCase(browser, item, credentials, options, redact, save) {
  let session;
  const result = { browser: options.browserInfo, id: item.id, page: item.page, role: item.role, path: item.path, locale: item.locale, theme: item.theme, requested_geometry: item.viewport, status: "recorded", findings: [], started_at: new Date().toISOString() };
  const start = performance.now();
  try {
    session = await createSession(browser, item, options, redact);
    if (item.role !== "anonymous") result.authentication = await signIn(session, item.role, credentials, options);
    session.phase.value = "capture";
    const navigationStart = performance.now();
    const response = await session.page.goto(options.base + item.path, { waitUntil: "domcontentloaded" });
    result.navigation_response_status = response?.status() ?? null;
    result.domcontentloaded_elapsed_ms = performance.now() - navigationStart;
    try {
      await session.page.locator("main h1").first().waitFor({ state: "visible" });
      result.main_heading_visible_elapsed_ms = performance.now() - navigationStart;
    } catch (error) { result.findings.push({ kind: "main_heading_not_visible", message: errorMessage(error) }); }
    result.readiness = await waitForReadQuiet(session.pendingReads, { quietMs: options.settle, timeoutMs: options.timeout });
    if (!result.readiness.complete) result.findings.push({ kind: "api_readiness_timeout", pending_count: result.readiness.pending_count, pending_reads: result.readiness.pending_reads });
    result.settle_window_ms = options.settle;
    const geometry = await measureGeometry(session.page, item.viewport);
    result.final_path = new URL(session.page.url()).pathname;
    const performanceData = await timingSnapshot(session.page);
    for (const group of ["navigation", "resources"]) performanceData[group] = performanceData[group].map(entry => ({ ...entry, name: safeUrl(entry.name) }));
    const prefix = join("cases", item.id);
    const png = await session.page.screenshot({ type: "png", fullPage: false, animations: "disabled", caret: "hide", scale: "css", mask: masks(session.page, credentials) });
    await writeFile(join(options.output, `${prefix}.viewport.png`), png, { mode: 0o600 });
    geometry.browser = options.browserInfo;
    performanceData.browser = options.browserInfo;
    geometry.screenshot = pngSize(png);
    geometry.checks = inspectGeometry(geometry);
    result.screenshot = { file: `${prefix}.viewport.png`, ...geometry.screenshot, mode: "viewport" };
    if (options.fullPage) {
      const full = await session.page.screenshot({ type: "png", fullPage: true, animations: "disabled", caret: "hide", scale: "css", mask: masks(session.page, credentials) });
      await writeFile(join(options.output, `${prefix}.full-page.png`), full, { mode: 0o600 });
      result.full_page_screenshot = { file: `${prefix}.full-page.png`, ...pngSize(full), mode: "full_page_not_viewport" };
    }
    await save(`${prefix}.geometry.json`, geometry);
    await save(`${prefix}.timings.json`, performanceData);
    result.geometry_file = `${prefix}.geometry.json`; result.timings_file = `${prefix}.timings.json`;
    if (geometry.checks.horizontalOverflowPx > 1) result.findings.push({ kind: "horizontal_page_overflow", pixels: geometry.checks.horizontalOverflowPx });
    for (const [check, matches] of Object.entries(geometry.checks)) if (check !== "horizontalOverflowPx" && !matches) result.findings.push({ kind: "geometry_mismatch", check });
    if (geometry.effective_locale !== (item.locale === "zh" ? "zh-CN" : "en") || geometry.effective_theme !== item.theme) result.findings.push({ kind: "locale_or_theme_mismatch", locale: geometry.effective_locale, theme: geometry.effective_theme });
    if (result.final_path !== item.path) result.findings.push({ kind: "unexpected_route", expected: item.path, actual: result.final_path });
    if (session.events.page_errors.length) result.findings.push({ kind: "uncaught_page_errors", count: session.events.page_errors.length });
    const consoleEvents = classifyConsoleEvents(session.events.console, session.events.network, options.base);
    const consoleErrors = consoleEvents.filter(event => event.classification === "unexpected_error");
    result.expected_bootstrap_401 = { responses: session.events.network.filter(event => isExpectedBootstrap401(event, options.base)).length, console_messages: consoleEvents.filter(event => event.classification === "expected_account_bootstrap_401").length };
    if (consoleErrors.length) result.findings.push({ kind: "console_errors", count: consoleErrors.length });
    const failedResponses = session.events.network.filter(event => event.event === "response" && event.status >= 400 && !isExpectedBootstrap401(event, options.base));
    if (failedResponses.length) result.findings.push({ kind: "http_errors", count: failedResponses.length });
    if (session.events.blocked_requests.length) result.findings.push({ kind: "blocked_requests", count: session.events.blocked_requests.length });
    result.rendered_states = await session.page.locator('main [role="alert"], main .admin-state, main .workspace-state, .route-loading, .route-error').evaluateAll(elements => elements.map(element => ({ role: element.getAttribute("role"), classes: element.className, text: element.textContent?.slice(0, 500) })));
  } catch (error) { result.status = "failed"; result.error = errorMessage(error); }
  finally {
    if (session) {
      session.events.console = classifyConsoleEvents(session.events.console, session.events.network, options.base);
      session.events.pending_reads_at_close = session.pendingReads.snapshot();
      session.events.superseded_document_reads_at_close = session.pendingReads.supersededSnapshot();
      await save(join("cases", `${item.id}.events.json`), session.events);
      result.events_file = join("cases", `${item.id}.events.json`);
      await session.context.close();
    }
  }
  result.elapsed_ms = performance.now() - start;
  return redact(result);
}
async function collectBoundaries(browser, variant, role, credentials, options, redact, save) {
  const id = `boundary-${role}-${variant.viewport.width}x${variant.viewport.height}-${variant.locale}-${variant.theme}`;
  const result = { browser: options.browserInfo, id, role, locale: variant.locale, theme: variant.theme, requested_geometry: variant.viewport, status: "recorded", checks: [], findings: [] };
  let session;
  async function step(name, action) {
    session.phase.value = `boundary_${name}`;
    const start = performance.now();
    try { const details = await action(); result.checks.push(redact({ name, outcome: "matched", elapsed_ms: performance.now() - start, ...details })); }
    catch (error) { result.checks.push(redact({ name, outcome: "failed", elapsed_ms: performance.now() - start, message: errorMessage(error) })); result.findings.push({ kind: "boundary_mismatch", check: name }); }
  }
  const require = (value, message) => { if (!value) throw new Error(message); };
  try {
    session = await createSession(browser, variant, options, redact);
    const auth = await signIn(session, role, credentials, options, role === "admin" ? "/workspace/tasks" : "/admin/users");
    result.checks.push({ name: "login_role_destination", outcome: auth.landed_path === (role === "admin" ? "/admin/overview" : "/workspace/new") ? "matched" : "failed", ...auth });
    if (result.checks[0].outcome === "failed") result.findings.push({ kind: "boundary_mismatch", check: "login_role_destination" });
    await step("direct_role_boundary", async () => {
      const index = session.events.network.length;
      const path = role === "admin" ? "/workspace/tasks" : "/admin/users";
      await session.page.goto(options.base + path, { waitUntil: "domcontentloaded" });
      if (role === "admin") { await session.page.waitForURL(url => url.pathname === "/admin/overview"); await session.page.locator(".admin-nav").waitFor(); require(await session.page.locator('.workspace-create, .workspace-recent').count() === 0, "Admin mounted ordinary workspace content"); }
      else { await session.page.locator(".route-error").waitFor(); require(await session.page.locator(".admin-nav").count() === 0, "Ordinary account mounted admin navigation"); }
      await session.page.waitForTimeout(options.settle);
      const requests = session.events.network.slice(index).filter(event => event.event === "response");
      const forbidden = requests.filter(event => role === "user" ? new URL(event.url).pathname.startsWith("/api/v1/admin/") : /^\/api\/v1\/(tasks|profiles|analyst|api-keys)(\/|$)/.test(new URL(event.url).pathname));
      require(forbidden.length === 0, "Role-forbidden UI data requests observed");
      return { attempted_path: path, landed_path: new URL(session.page.url()).pathname, forbidden_request_count: forbidden.length };
    });
    if (role === "admin") await step("api_keys_route_boundary", async () => {
      await session.page.goto(options.base + "/api/keys", { waitUntil: "domcontentloaded" });
      await session.page.waitForURL(url => url.pathname === "/admin/overview");
      return { attempted_path: "/api/keys", landed_path: new URL(session.page.url()).pathname };
    });
    await step("server_role_boundary", async () => {
      const path = role === "user" ? "/api/v1/admin/overview" : "/api/v1/tasks?page=1&page_size=1";
      const response = await session.context.request.get(options.base + path);
      require(response.status() === 403, "Server did not return 403 for the role-forbidden resource");
      return { path: safeUrl(options.base + path), http_status: response.status() };
    });
    await step("header_account_scope", async () => {
      await session.page.goto(options.base + "/", { waitUntil: "domcontentloaded" });
      await openPublicAccount(session.page);
      const links = await session.page.locator("#account-dropdown a").evaluateAll(elements => elements.map(element => element.getAttribute("href")));
      const expected = role === "admin" ? "/admin" : "/workspace/new";
      require(links.includes(expected) && !links.some(path => role === "admin" ? path?.startsWith("/workspace") : path?.startsWith("/admin")), "Header account link crosses role scope");
      const png = await session.page.screenshot({ fullPage: false, scale: "css", animations: "disabled", mask: masks(session.page, credentials) });
      const geometry = await measureGeometry(session.page, variant.viewport);
      geometry.browser = options.browserInfo; geometry.screenshot = pngSize(png); geometry.checks = inspectGeometry(geometry);
      const geometryFile = join("boundaries", `${id}.account.geometry.json`);
      await save(geometryFile, geometry);
      const file = join("boundaries", `${id}.account.viewport.png`);
      await writeFile(join(options.output, file), png, { mode: 0o600 });
      return { links, geometry_file: geometryFile, screenshot: { file, ...pngSize(png) } };
    });
    await step("logout", async () => {
      // This independent step restores its own UI prerequisite if the previous one failed.
      if (await session.page.locator("#account-dropdown button").count() === 0) {
        await session.page.goto(options.base + "/", { waitUntil: "domcontentloaded" });
        await openPublicAccount(session.page);
      }
      const responsePromise = session.page.waitForResponse(response => new URL(response.url()).pathname === "/api/v1/logout" && response.request().method() === "POST");
      await session.page.locator("#account-dropdown button.account-logout").click();
      const response = await responsePromise;
      require(response.ok(), "Logout request failed");
      await session.page.locator(".login-link").waitFor({ state: "attached" });
      const me = await session.context.request.get(options.base + "/api/v1/users/me");
      require(me.status() === 401, "Logout left an authenticated cookie session");
      return { logout_status: response.status(), me_status: me.status(), landed_path: new URL(session.page.url()).pathname };
    });
  } catch (error) { result.status = "failed"; result.error = errorMessage(error); result.checks.push({ name: "remaining_boundaries", outcome: "not_run", reason: "Authentication or setup failed" }); }
  finally { if (session) {
    session.events.console = classifyConsoleEvents(session.events.console, session.events.network, options.base);
    session.events.pending_reads_at_close = session.pendingReads.snapshot();
    session.events.superseded_document_reads_at_close = session.pendingReads.supersededSnapshot();
    await save(join("boundaries", `${id}.events.json`), session.events); await session.context.close();
  } }
  return redact(result);
}
export async function main(argv = process.argv.slice(2)) {
  const options = parseOptions(argv);
  if (options.help) {
    console.log("Usage: node frontend/scripts/capture-closeout.mjs --output-dir runtime/<new-evidence-dir> [--mode dry-run|smoke|capture] [--browser auto|chrome|chromium] [--executable-path /absolute/path/to/browser] [--sizes 320x900,390x900,768x900,1440x900,1920x900] [--locales zh,en] [--themes light,dark] [--pages home,login,register,new,tasks,profiles,settings,api/docs,api/keys,admin-overview,admin-users,admin-scheduling,admin-quotas,admin-operations,admin-audit] [--full-page]\nOnly http://127.0.0.1:8013 is supported. Paths resolve from repository root. Dry-run reads no credentials and opens no browser. Smoke is bounded to four page cases plus one geometry's ordinary/admin role checks.");
    return 0;
  }
  const plan = buildPlan(options);
  if (options.mode === "dry-run") { console.log(JSON.stringify(plan, null, 2)); return 0; }
  await assertOutputDirectory(options.output);
  const credentials = await readFixture(options.credentials), redact = makeRedactor(credentials);
  await mkdir(join(options.output, "cases"), { recursive: true, mode: 0o700 });
  await mkdir(join(options.output, "boundaries"), { mode: 0o700 });
  const save = (file, value) => writeFile(join(options.output, file), JSON.stringify(redact(value), null, 2) + "\n", { mode: 0o600 });
  await save("plan.json", plan);
  const summary = { schema_version: 1, scope: plan.scope, started_at: new Date().toISOString(), base_url: options.base, evidence_dir: options.output, status: "running", browser: null, cases: [], boundaries: [] };
  let browser;
  try {
    const launched = await launchBrowser(options); browser = launched.browser; summary.browser = launched.info; options.browserInfo = launched.info;
    await save("summary.json", summary);
    summary.cases = await captureCases(plan.cases, item => collectCase(browser, item, credentials, options, redact, save), async result => {
      await appendFile(join(options.output, "cases.jsonl"), JSON.stringify(redact(result)) + "\n", { mode: 0o600 });
    });
    const boundaryCases = plan.boundary_variants.flatMap(variant => ["user", "admin"].map(role => ({ ...variant, role, id: `boundary-${role}-${variant.viewport.width}x${variant.viewport.height}-${variant.locale}-${variant.theme}` })));
    summary.boundaries = await captureCases(boundaryCases, item => collectBoundaries(browser, item, item.role, credentials, options, redact, save), async result => {
      await appendFile(join(options.output, "boundaries.jsonl"), JSON.stringify(redact(result)) + "\n", { mode: 0o600 });
    });
    const all = [...summary.cases, ...summary.boundaries];
    summary.counts = { planned_pages: plan.cases.length, recorded_pages: summary.cases.filter(item => item.status === "recorded").length, failed_cases: all.filter(item => item.status === "failed").length, cases_with_findings: all.filter(item => item.findings?.length).length, boundary_groups: summary.boundaries.length };
    summary.status = summary.counts.failed_cases || summary.counts.cases_with_findings ? "completed_with_findings" : "recorded_without_detected_findings";
  } catch (error) { summary.status = "setup_failed"; summary.error = redact(errorMessage(error)); }
  finally { await browser?.close(); summary.completed_at = new Date().toISOString(); await save("summary.json", summary); }
  console.log(JSON.stringify({ scope: summary.scope, status: summary.status, browser: summary.browser?.name || "not launched", counts: summary.counts || null, evidence_dir: options.output }));
  return summary.status === "recorded_without_detected_findings" ? 0 : 2;
}
if (process.argv[1] && import.meta.url === pathToFileURL(resolve(process.argv[1])).href) {
  main().then(code => { process.exitCode = code; }).catch(() => { console.error("Capture setup failed. Check arguments, the isolated fixture, and the new runtime evidence path. No credentials were logged."); process.exitCode = 2; });
}
