export type PreviewImage = { locale: "zh" | "en"; theme: "light" | "dark"; viewport: "desktop" | "mobile"; kind: "main" | "analyst"; src: string; width: number; height: number; pixel_ratio: 2; report_id: string; report_hash: string; model: string; facts_hash: string };
export type PreviewManifest = { version: 2; source: { kind: "preset"; id: "quick-demo"; href: "/workspace/examples/quick-demo#analyst" }; captured_at: string; verification: { provider: "glm"; verified: true }; images: PreviewImage[] };
export function parsePreviewManifest(value: unknown): PreviewManifest | null {
  if (!value || typeof value !== "object") return null;
  const data = value as PreviewManifest;
  if (data.version !== 2 || data.source?.kind !== "preset" || data.source.id !== "quick-demo" || data.source.href !== "/workspace/examples/quick-demo#analyst" || !Number.isFinite(Date.parse(data.captured_at)) || data.verification?.provider !== "glm" || data.verification.verified !== true || !Array.isArray(data.images) || data.images.length !== 16) return null;
  const keys = new Set<string>(); const reports = new Map<string, string>();
  const digest = /^[a-f0-9]{64}$/;
  for (const item of data.images) {
    if (!item || !["zh", "en"].includes(item.locale) || !["light", "dark"].includes(item.theme) || !["desktop", "mobile"].includes(item.viewport) || !["main", "analyst"].includes(item.kind) || !/^\/assets\/previews\/analyst\/[a-zA-Z0-9_-]+\.webp$/.test(item.src) || !Number.isInteger(item.width) || item.width <= 0 || !Number.isInteger(item.height) || item.height <= 0 || item.pixel_ratio !== 2 || !item.report_id || item.model !== "glm-5.3" || !digest.test(item.facts_hash) || !digest.test(item.report_hash)) return null;
    if (item.facts_hash !== data.images[0].facts_hash) return null;
    const report = `${item.report_id}:${item.report_hash}`;
    if (reports.has(item.locale) && reports.get(item.locale) !== report) return null;
    reports.set(item.locale, report);
    keys.add(`${item.locale}:${item.theme}:${item.viewport}:${item.kind}`);
  }
  return keys.size === 16 ? data : null;
}
