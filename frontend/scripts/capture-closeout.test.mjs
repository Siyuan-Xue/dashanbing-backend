import test from "node:test";
import assert from "node:assert/strict";
import { mkdtemp, rm, symlink } from "node:fs/promises";
import { join } from "node:path";
import { buildPlan, parseOptions, makeRedactor, inspectGeometry, captureCases, assertOutputDirectory, browserIdentity, waitForReadQuiet } from "./capture-closeout.mjs";
import * as helpers from "./capture-closeout.mjs";

const output = "runtime/closeout-test-evidence";
test("full capture expands all 15 pages into 300 exact viewport cases", () => {
  const plan = buildPlan(parseOptions(["--mode", "capture", "--output-dir", output]));
  assert.equal(plan.cases.length, 300);
  assert.equal(new Set(plan.cases.map(item => item.id)).size, 300);
  assert.deepEqual([...new Set(plan.cases.map(item => item.viewport.width))], [320, 390, 768, 1440, 1920]);
  assert.ok(plan.cases.every(item => item.screen.width === item.viewport.width && item.screen.height === 900 && item.deviceScaleFactor === 1));
  assert.deepEqual(plan.cases.filter(item => item.role === "admin").slice(0, 6).map(item => item.path), ["/admin/overview", "/admin/users", "/admin/scheduling", "/admin/quotas", "/admin/operations", "/admin/audit"]);
});
test("dry-run is the default and development smoke stays explicitly bounded", () => {
  assert.equal(parseOptions(["--output-dir", output]).mode, "dry-run");
  const plan = buildPlan(parseOptions(["--mode", "smoke", "--output-dir", output]));
  assert.equal(plan.cases.length, 4);
  assert.equal(plan.scope, "development_smoke_not_acceptance");
  assert.deepEqual(plan.cases.map(item => item.page), ["home", "login", "new", "admin-overview"]);
});
test("rejects non-fixture origins, ambiguous sizes and outputs outside ignored runtime", () => {
  for (const url of ["https://example.com", "http://127.0.0.1:8000", "http://name:password@127.0.0.1:8013", "http://127.0.0.1:8013/other"]) assert.throws(() => parseOptions(["--output-dir", output, "--base-url", url]));
  for (const sizes of ["320", "320x0", "320x900,320x900", "320x900,nope"]) assert.throws(() => parseOptions(["--output-dir", output, "--sizes", sizes]));
  assert.throws(() => parseOptions([]));
  assert.throws(() => parseOptions(["--output-dir", "frontend/public/evidence"]));
  assert.throws(() => parseOptions(["--output-dir", "runtime"]));
  assert.throws(() => parseOptions(["--output-dir", output, "--pages", "unknown"]));
});
test("redacts credential values, encoded values and bearer/cookie material recursively", () => {
  const redact = makeRedactor({ jwt_secret: "secret-for-test-123", admin: { username: "fixture-operator", password: "test password&789", token: "a.b.c" }, accounts: [{ username: "fixture-player", password: "private-player-pass" }] });
  const result = JSON.stringify(redact({ message: "fixture-operator test%20password%26789 private-player-pass Bearer unknown-token", nested: ["secret-for-test-123", "access_token=abc123", "Cookie: session=abc123"] }));
  for (const secret of ["fixture-operator", "test%20password%26789", "private-player-pass", "unknown-token", "secret-for-test-123", "abc123"]) assert.equal(result.includes(secret), false);
  assert.ok(result.includes("[REDACTED]"));
});
test("records geometry independently of screenshot dimensions without treating long pages as overflow", () => {
  const good = inspectGeometry({ requested: { width: 320, height: 900 }, viewport: { width: 320, height: 900 }, screen: { width: 320, height: 900 }, document: { scrollWidth: 320, scrollHeight: 2600 }, screenshot: { width: 320, height: 900 } });
  assert.equal(good.horizontalOverflowPx, 0); assert.equal(good.exactViewportScreenshot, true);
  const bad = inspectGeometry({ requested: { width: 320, height: 900 }, viewport: { width: 320, height: 900 }, screen: { width: 320, height: 900 }, document: { scrollWidth: 420, scrollHeight: 2600 }, screenshot: { width: 640, height: 1800 } });
  assert.equal(bad.horizontalOverflowPx, 100); assert.equal(bad.exactViewportScreenshot, false);
});
test("per-case failures are retained and do not stop subsequent captures or rerun them", async () => {
  const visited = [], records = [];
  const results = await captureCases([{ id: "a" }, { id: "b" }, { id: "c" }], async item => { visited.push(item.id); if (item.id === "b") throw new Error("fixture failure"); return { id: item.id, status: "recorded" }; }, async item => records.push(item));
  assert.deepEqual(visited, ["a", "b", "c"]);
  assert.equal(results.length, 3); assert.equal(records[1].status, "failed"); assert.equal(results[2].status, "recorded");
});
test("evidence path rejects existing and escaping symlink directories", async () => {
  const root = await mkdtemp(join(process.cwd(), "runtime-closeout-test-"));
  try {
    await assert.rejects(assertOutputDirectory(root, root));
    await symlink("/tmp", join(root, "escape"));
    await assert.rejects(assertOutputDirectory(join(root, "escape", "new"), root));
    await assert.doesNotReject(assertOutputDirectory(join(root, "new"), root));
  } finally { await rm(root, { recursive: true, force: true }); }
});

test("browser evidence distinguishes actual Chrome from Chromium and unknown executables", () => {
  assert.equal(browserIdentity("Google Chrome 152.0.7977.83", "/Users/test/Applications/Google Chrome.app/Contents/MacOS/Google Chrome").name, "Google Chrome");
  assert.equal(browserIdentity("Chromium 150.0.1234.0", "/opt/chromium").name, "Chromium");
  assert.equal(browserIdentity("152.0.7977.83", "/tmp/browser").name, "Unverified Chromium-family executable");
  const options = parseOptions(["--output-dir", "runtime/capture", "--executable-path", "/Users/test/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"]);
  assert.equal(options.executablePath, "/Users/test/Applications/Google Chrome.app/Contents/MacOS/Google Chrome");
});

test("readiness waits for pending HTTP reads and records a timeout without retrying", async () => {
  let clock = 0; const pending = new Set(["settings"]);
  const ready = await waitForReadQuiet(pending, { quietMs: 10, timeoutMs: 100, now: () => clock, sleep: async ms => { clock += ms; if (clock >= 30) pending.clear(); } });
  assert.equal(ready.complete, true); assert.ok(ready.elapsed_ms >= 40);
  clock = 0; pending.add("never-finishes");
  const timedOut = await waitForReadQuiet(pending, { quietMs: 10, timeoutMs: 50, now: () => clock, sleep: async ms => { clock += ms; } });
  assert.equal(timedOut.complete, false); assert.equal(timedOut.pending_count, 1);
});

test("public account controls open the mobile menu first and preserve already-open/desktop menus", async () => {
  for (const initial of [{ mobile: true, menu: false }, { mobile: true, menu: true }, { mobile: false, menu: false }]) {
    const state = { ...initial, account: false }, clicks = [];
    const visible = selector => selector === ".public-menu-toggle" ? state.mobile : selector === ".account-link" ? !state.mobile || state.menu : state.account;
    const page = { locator: selector => ({
      waitFor: async ({ state: required = "visible" } = {}) => { if (required !== "attached") assert.ok(visible(selector), `${selector} must be visible`); },
      isVisible: async () => visible(selector),
      getAttribute: async () => String(selector === ".public-menu-toggle" ? state.menu : state.account),
      click: async () => { assert.ok(visible(selector), `Cannot click hidden ${selector}`); clicks.push(selector); if (selector === ".public-menu-toggle") state.menu = !state.menu; else state.account = !state.account; },
    }) };
    await helpers.openPublicAccount(page);
    await helpers.openPublicAccount(page);
    assert.equal(state.account, true);
    assert.deepEqual(clicks, initial.mobile && !initial.menu ? [".public-menu-toggle", ".account-link"] : [".account-link"]);
  }
});

test("only endpoint/status-correlated anonymous bootstrap 401 console errors are expected", () => {
  const base = "http://127.0.0.1:8013", url = `${base}/api/v1/users/me`;
  const response = { event: "response", method: "GET", url, status: 401, authenticated_at_start: false, at_ms: 100 };
  assert.equal(helpers.isExpectedBootstrap401(response, base), true);
  for (const change of [{ url: `${base}/api/v1/tasks` }, { url: "http://elsewhere/api/v1/users/me" }, { status: 500 }, { authenticated_at_start: true }, { authenticated_at_start: undefined }, { method: "POST" }]) {
    assert.equal(helpers.isExpectedBootstrap401({ ...response, ...change }, base), false);
  }
  const native = { type: "error", text: "Failed to load resource: the server responded with a status of 401 (Unauthorized)", location: { url }, at_ms: 110 };
  const events = [native, { ...native, location: { url: `${base}/api/v1/tasks` } }, { ...native, text: "Application error 401" }, { ...native, location: { url: `${base}/assets/app.js` } }, { ...native, at_ms: 10000 }];
  const classified = helpers.classifyConsoleEvents(events, [response], base);
  assert.deepEqual(classified.map(event => event.classification), ["expected_account_bootstrap_401", ...Array(4).fill("unexpected_error")]);
  assert.equal(classified[0].text, native.text);
  assert.equal(events[0].classification, undefined, "Retain the original event data");
  for (const responseChange of [{ status: 500 }, { authenticated_at_start: true }]) assert.equal(helpers.classifyConsoleEvents([native], [{ ...response, ...responseChange }], base)[0].classification, "unexpected_error");
});

test("browser read lifecycle removes cancellation/end/redirect entries without aging out outstanding requests", async () => {
  let clock = 0;
  const base = "http://127.0.0.1:8013", tracker = helpers.createApiReadTracker(base, () => clock);
  const start = (requestId, loaderId, path = "/api/v1/tasks") => tracker.start({ requestId, loaderId, frameId: "main", timestamp: clock / 1000, request: { url: base + path, method: "GET" } });
  start("old", "before-navigation"); start("new", "after-navigation");
  tracker.end({ requestId: "old", canceled: true, errorText: "net::ERR_ABORTED" }, "loadingFailed");
  tracker.response({ requestId: "new", response: { status: 200 } });
  assert.equal(tracker.size, 1, "Response headers alone do not complete the body");
  tracker.end({ requestId: "new" }, "loadingFinished");
  tracker.end({ requestId: "old" }, "loadingFinished");
  assert.equal(tracker.size, 0, "Duplicate/late terminal events are harmless");
  start("redirect", "after-navigation"); start("redirect", "after-navigation", "/login");
  assert.equal(tracker.size, 0, "Redirect outside API ends API-read tracking");
  start("hung", "after-navigation");
  const timedOut = await waitForReadQuiet(tracker, { quietMs: 10, timeoutMs: 50, now: () => clock, sleep: async ms => { clock += ms; } });
  assert.equal(timedOut.complete, false); assert.equal(timedOut.pending_count, 1);
  assert.equal(timedOut.pending_reads[0].request_id, "hung");
  assert.equal(timedOut.pending_reads[0].loader_id, "after-navigation");
  assert.ok(timedOut.pending_reads[0].age_ms >= 50);
  tracker.end({ requestId: "hung" }, "loadingFinished");
  const ready = await waitForReadQuiet(tracker, { quietMs: 10, timeoutMs: 50, now: () => clock, sleep: async ms => { clock += ms; } });
  assert.equal(ready.complete, true); assert.deepEqual(ready.pending_reads, []);
});

test("document replacement archives old-loader reads as unresolved evidence while current/unknown-loader reads still time out", async () => {
  let clock = 0;
  const tracker = helpers.createApiReadTracker("http://127.0.0.1:8013", () => clock);
  const start = (requestId, loaderId) => tracker.start({ requestId, loaderId, frameId: "main", request: { method: "GET", url: "http://127.0.0.1:8013/api/v1/tasks" } });
  tracker.navigate({ id: "main", loaderId: "old" });
  start("missing-end", "old"); start("new-hung", "new"); start("unknown-loader", "");
  const retired = tracker.navigate({ id: "main", loaderId: "new" });
  assert.deepEqual(retired.map(entry => entry.request_id), ["missing-end"]);
  assert.equal(retired[0].terminal, null, "Document replacement must not fabricate request completion");
  start("late-old-start", "old");
  const timedOut = await waitForReadQuiet(tracker, { quietMs: 10, timeoutMs: 50, now: () => clock, sleep: async ms => { clock += ms; } });
  assert.equal(timedOut.complete, false);
  assert.deepEqual(timedOut.pending_reads.map(entry => entry.request_id), ["new-hung", "unknown-loader"]);
  assert.deepEqual(timedOut.superseded_document_reads.map(entry => entry.request_id), ["missing-end", "late-old-start"]);
  tracker.end({ requestId: "missing-end", canceled: true, errorText: "net::ERR_ABORTED" }, "loadingFailed");
  assert.deepEqual(tracker.supersededSnapshot().map(entry => entry.request_id), ["late-old-start"]);
  tracker.end({ requestId: "new-hung" }, "loadingFinished"); tracker.end({ requestId: "unknown-loader" }, "loadingFinished");
  const ready = await waitForReadQuiet(tracker, { quietMs: 10, timeoutMs: 50, now: () => clock, sleep: async ms => { clock += ms; } });
  assert.equal(ready.complete, true); assert.equal(ready.superseded_document_reads.length, 1);
  assert.equal(ready.scope, "current_main_document_api_reads");
});
