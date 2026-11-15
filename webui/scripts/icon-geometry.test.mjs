import assert from "node:assert/strict";
import test from "node:test";
import { ICON_GRID, ICON_SIZE_TOKENS, icons } from "../src/lib/iconGeometries.ts";

// Alignment is audited against real browser rasterization, not a path parser.
// Run `node scripts/icon-measure.mjs` after editing an icon path.
test("every icon uses the same 24 grid and one stroke width", () => {
  assert.equal(ICON_GRID, 24);
  for (const [name, icon] of Object.entries(icons)) {
    assert.equal(icon.grid, 24, `${name} must use the 24 grid`);
    assert.equal(icon.stroke, 1.5, `${name} must use the shared stroke width`);
  }
});

test("every icon path is present and parses", () => {
  for (const [name, icon] of Object.entries(icons)) {
    assert.match(icon.path, /^[Mm]/, `${name} must start with a move command`);
    assert.ok((icon.path.match(/[a-zA-Z]/g) ?? []).every(command => /[MmLlHhVvCcSsQqAaZz]/.test(command)), `${name} uses an unsupported command`);
  }
});

test("size tokens use only the approved scale", () => {
  assert.deepEqual(ICON_SIZE_TOKENS, { xs: 14, sm: 16, md: 18, lg: 20, xl: 24 });
});
