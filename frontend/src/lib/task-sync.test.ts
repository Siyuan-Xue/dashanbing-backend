import { expect, test } from "vitest";
import { adjacentFrameTime, alignmentFor, nearestFrameTime } from "./task-sync";

test("frame stepping uses measured timestamps, tie selects earlier, and stops at boundaries", () => {
  const timestamps = [0, 33.367, 66.734, 100.101];
  expect(nearestFrameTime(timestamps, 50.0505)).toBe(33.367);
  expect(adjacentFrameTime(timestamps, 33.367, 1)).toBe(66.734);
  expect(adjacentFrameTime(timestamps, 66.734, -1)).toBe(33.367);
  expect(adjacentFrameTime(timestamps, 0, -1)).toBe(0);
  expect(adjacentFrameTime(timestamps, 100.101, 1)).toBe(100.101);
});

test("linked preview derives cam03 anchored offsets and common overlap with mixed start times", () => {
  expect(alignmentFor({ cam_01: 100, cam_02: 300, cam_03: 200, cam_04: 250 }, { cam_01: 500, cam_02: 450, cam_03: 600, cam_04: 700 })).toEqual({
    offsets: { cam_01: -100, cam_02: 100, cam_03: 0, cam_04: 50 }, start: 100, end: 350,
  });
  expect(alignmentFor({ cam_01: 900, cam_02: 0, cam_03: 100, cam_04: 0 }, { cam_01: 400, cam_02: 400, cam_03: 400, cam_04: 400 })).toBeNull();
  expect(alignmentFor({ cam_01: NaN, cam_02: 0, cam_03: 0, cam_04: 0 }, { cam_01: 400, cam_02: 400, cam_03: 400, cam_04: 400 })).toBeNull();
});
