import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import { fileURLToPath } from "node:url";

import {
  formatPercent,
  isHotspotHit,
  validateHotspot,
} from "../static/puzzles/hotspot.js";

const cases = JSON.parse(
  readFileSync(
    fileURLToPath(
      new URL("../static/puzzles/hotspot_hit_cases.json", import.meta.url),
    ),
    "utf8",
  ),
);

test("hotspot browser hit testing matches the shared Python cases", () => {
  for (const example of cases) {
    assert.deepEqual(
      isHotspotHit(
        example.regions,
        example.tolerance,
        example.x,
        example.y,
      ),
      example.expected,
      example.name,
    );
  }
});

test("hotspot editor reports live warnings and formats percentages", () => {
  const tooMany = validateHotspot(
    Array.from({ length: 51 }, () => ({ x: 1, y: 1, w: 2, h: 2 })),
    0,
  );
  assert.match(tooMany.errors[0], /maximum of 50 regions/);

  const narrow = validateHotspot(
    [{ x: 10, y: 10, w: 1, h: 1 }],
    0,
  );
  assert.equal(narrow.errors.length, 0);
  assert.match(narrow.warnings[0], /very small/);

  const overlap = validateHotspot(
    [
      { x: 10, y: 10, w: 30, h: 50 },
      { x: 20, y: 10, w: 30, h: 50 },
    ],
    0,
  );
  assert.equal(overlap.warnings.some((warning) => warning.includes("cover")), false);

  const broad = validateHotspot(
    [{ x: 10, y: 10, w: 60, h: 50 }],
    0,
  );
  assert.match(broad.warnings[0], /cover 30%/);
  assert.equal(formatPercent(56), "56");
  assert.equal(formatPercent(56.25), "56.3");
});
