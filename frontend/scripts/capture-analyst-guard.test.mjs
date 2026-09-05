import { test } from "node:test";
import assert from "node:assert/strict";
import { assertVerifiedReport, captureClips, assertCaptureMatrix } from "./capture-analyst-guard.mjs";
const valid = () => ({ status: "completed", facts: { evidence: [{ id: "event-1" }] }, subjects: [], provenance: { provider: "glm", verified: true, facts_hash: "a".repeat(64) }, report: { id: "test-report", summary: "Fixture only", model: "glm-5.3", locale: "zh", style: "coach", highlights: [{ text: "Fixture", evidence_ids: ["event-1"] }], players: [], suggestions: ["Fixture"], comparison: null } });
test("accepts a live-verified report only when current facts match", () => { assert.equal(assertVerifiedReport(valid(), "zh", "a".repeat(64)).id, "test-report"); });
test("refuses disabled, missing provenance, mocked models, stale facts, and invalid citations", () => {
  for (const patch of [{ status: "disabled" }, { provenance: null }, { provenance: { provider: "glm", verified: false, facts_hash: "a".repeat(64) } }, { report: { ...valid().report, model: "mock" } }, { report: { ...valid().report, highlights: [{ text: "Fixture", evidence_ids: ["unknown"] }] } }]) assert.throws(() => assertVerifiedReport({ ...valid(), ...patch }, "zh", "a".repeat(64)));
  assert.throws(() => assertVerifiedReport(valid(), "zh", "b".repeat(64)));
  assert.throws(() => assertVerifiedReport(valid(), "en", "a".repeat(64)));
});

test("rejects named or linked subjects and unrelated report players", () => {
  for (const subjects of [[{ id: "s1", label: "Alex" }], [{ id: "s1", label: "球员 1", profile_id: "private-profile" }]]) {
    assert.throws(() => assertVerifiedReport({ ...valid(), subjects }, "zh", "a".repeat(64)));
  }
  const state = valid(); state.report.players = [{ subject_id: "unknown", text: "Fixture", evidence_ids: [] }];
  assert.throws(() => assertVerifiedReport(state, "zh", "a".repeat(64)));
});

test("all 16 crops preserve video/data/analyst order and exclude the intervening raw tabs", () => {
  for (const viewport of ["desktop", "mobile"]) {
    const mobile = viewport === "mobile";
    const width = mobile ? 358 : 1120;
    const video = { x: 16, y: 200, width, height: mobile ? 202 : 630 };
    const raw = { x: 16, y: video.y + video.height + 16, width, height: 400 };
    const analyst = { x: 16, y: raw.y + raw.height + 16, width, height: 1800 };
    const y = analyst.y + 150;
    const layout = { video, raw, analyst, report: { x: 16, y, width, height: 1450 }, composer: { x: 16, y: analyst.y + 1700, width, height: 76 }, summaryLines: [y + 68, y + 96], textLines: Array.from({ length: 50 }, (_, i) => y + 68 + i * 28) };
    for (const locale of ["zh", "en"]) for (const theme of ["light", "dark"]) {
      const clips = captureClips(layout, viewport);
      assert.equal(clips.main.height, video.height);
      assert.equal(clips.main.y, video.y);
      assert.ok(clips.main.y + clips.main.height <= raw.y);
      assert.equal(clips.analyst.y, analyst.y);
      assert.equal(clips.analyst.width, analyst.width);
      assert.equal(clips.analyst.height, analyst.height);
      assert.ok(clips.analyst.y + clips.analyst.height >= Math.max(...layout.textLines));
      assert.ok(clips.analyst.y + clips.analyst.height >= layout.composer.y + layout.composer.height);
      assert.ok(clips.analyst.y >= raw.y + raw.height, `${locale}/${theme}/${viewport}`);
    }
    assert.throws(() => captureClips({ ...layout, analyst: { ...analyst, y: video.y } }, viewport));
    assert.throws(() => captureClips({ ...layout, summaryLines: [] }, viewport));
    assert.throws(() => captureClips({ ...layout, analyst: { ...analyst, height: 500 } }, viewport));
  }
});

test("publishes only a complete 16-image matrix from the same facts and stable localized report", () => {
  const images = ["zh", "en"].flatMap(locale => ["light", "dark"].flatMap(theme => ["desktop", "mobile"].flatMap(viewport => ["main", "analyst"].map(kind => ({ locale, theme, viewport, kind, pixel_ratio: 2, width: 708, height: 800, facts_hash: "a".repeat(64), report_id: locale, report_hash: (locale === "zh" ? "b" : "c").repeat(64) })))));
  assert.doesNotThrow(() => assertCaptureMatrix(images));
  for (const patch of [{ facts_hash: "d".repeat(64) }, { report_id: "other" }, { report_hash: "d".repeat(64) }, { pixel_ratio: 1 }, { kind: "other" }]) {
    assert.throws(() => assertCaptureMatrix(images.map((image, i) => i ? image : { ...image, ...patch })));
  }
  assert.throws(() => assertCaptureMatrix(images.slice(0, 8)));
});
