import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { createRequire } from 'node:module';
import test from 'node:test';
import { runInNewContext } from 'node:vm';

const require = createRequire(import.meta.url);
const { transformSync } = require('next/dist/build/swc');

function loadLayout() {
  const source = readFileSync(new URL('../src/lib/timelineLayout.ts', import.meta.url), 'utf8');
  const { code } = transformSync(source, { jsc: { parser: { syntax: 'typescript' } }, module: { type: 'commonjs' } });
  const module = { exports: {} };
  runInNewContext(code, { exports: module.exports, module });
  return module.exports;
}

function timeline() {
  const element = Object.assign(new EventTarget(), { scrollLeft: 200, getBoundingClientRect: () => ({ left: 100, width: 800 }) });
  const positions = [];
  const module = { exports: {} };
  const source = readFileSync(new URL('../src/lib/timelineZoom.ts', import.meta.url), 'utf8');
  const { code } = transformSync(source, { jsc: { parser: { syntax: 'typescript' } }, module: { type: 'commonjs' } });
  runInNewContext(code, { exports: module.exports, module });
  const dispose = module.exports.bindTimelineZoom({ element, zoom: 2, onZoom: value => positions.push(value) });
  const wheel = (properties = {}) => {
    const event = Object.assign(new Event('wheel', { cancelable: true }), { deltaY: -100, clientX: 500, ctrlKey: false, metaKey: false, ...properties });
    element.dispatchEvent(event);
    return event;
  };
  return { wheel, positions, dispose };
}

test('Ctrl wheel zooms around the pointer and prevents browser zoom', () => {
  const { wheel, positions } = timeline();
  assert.equal(wheel({ ctrlKey: true }).defaultPrevented, true);
  assert.equal(positions[0].zoom, 4);
  assert.equal(positions[0].scrollLeft, 800);
});

test('ordinary wheel keeps scrolling without changing zoom', () => {
  const { wheel, positions } = timeline();
  assert.equal(wheel().defaultPrevented, false);
  assert.equal(positions.length, 0);
});

test('minimum zoom fits the timeline viewport with no horizontal overflow', () => {
  const { wheel, positions } = timeline();
  wheel({ ctrlKey: true, deltaY: 100 });
  assert.equal(positions.at(-1).zoom, 1);
  assert.equal(positions.at(-1).scrollLeft, 0);
  assert.equal(loadLayout().timelineWidth(800, positions.at(-1).zoom), 800);
});

test('Meta wheel zooms out and cleanup removes interception', () => {
  const { wheel, positions, dispose } = timeline();
  assert.equal(wheel({ metaKey: true, deltaY: 100 }).defaultPrevented, true);
  assert.equal(positions[0].zoom, 1);
  assert.equal(positions[0].scrollLeft, 0);
  dispose();
  assert.equal(wheel({ ctrlKey: true }).defaultPrevented, false);
});
