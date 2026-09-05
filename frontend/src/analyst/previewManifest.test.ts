import { expect, test } from "vitest";
import { parsePreviewManifest } from "./previewManifest";
import { previewFixture as manifest } from "../test/analystPreviewFixture";
test("accepts only all 16 main/detail variants of one verified session with retina mobile assets", () => {
  expect(parsePreviewManifest(manifest())).not.toBeNull();
  expect(parsePreviewManifest({ ...manifest(), images: manifest().images.slice(0, 8) })).toBeNull();
  expect(parsePreviewManifest({ ...manifest(), verification: { provider: "glm", verified: false } })).toBeNull();
  for (const patch of [{ src: "https://example.com/mock.webp" }, { src: "/assets/previews/analyst/../mock.webp" }, { report_id: "different-report" }, { report_hash: "d".repeat(64) }, { facts_hash: "d".repeat(64) }, { pixel_ratio: 1 }]) {
    const invalid = manifest(); Object.assign(invalid.images[0], patch);
    expect(parsePreviewManifest(invalid)).toBeNull();
  }
});
