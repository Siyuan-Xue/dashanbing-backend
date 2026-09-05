// Test-only static asset metadata; no fixture output is shipped as a real report
export function previewFixture() {
  const images = ["zh", "en"].flatMap(locale =>
    ["light", "dark"].flatMap(theme =>
      ["desktop", "mobile"].flatMap(viewport =>
        ["main", "analyst"].map(kind => ({
          locale, theme, viewport, kind,
          src: `/assets/previews/analyst/${locale}-${theme}-${viewport}-${kind}.webp`,
          width: viewport === "desktop" ? (kind === "main" ? 2240 : 1440) : 708,
          height: kind === "main" ? 1000 : 800, pixel_ratio: 2,
          report_id: `fixture-report-${locale}`, report_hash: (locale === "zh" ? "b" : "c").repeat(64),
          model: "glm-5.3", facts_hash: "a".repeat(64),
        })),
      ),
    ),
  );
  return {
    version: 2,
    source: { kind: "preset", id: "quick-demo", href: "/workspace/examples/quick-demo#analyst" },
    captured_at: "2026-09-05T00:00:00Z",
    verification: { provider: "glm", verified: true }, images,
  };
}
