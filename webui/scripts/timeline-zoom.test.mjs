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

function loadZoom() {
  const module = { exports: {} };
  const source = readFileSync(new URL('../src/lib/timelineZoom.ts', import.meta.url), 'utf8');
  const { code } = transformSync(source, { jsc: { parser: { syntax: 'typescript' } }, module: { type: 'commonjs' } });
  runInNewContext(code, { exports: module.exports, module });
  return module.exports;
}

function dispatchWheel(target, properties = {}) {
  const event = Object.assign(new Event('wheel', { cancelable: true }), { deltaY: -100, clientX: 500, ctrlKey: false, metaKey: false, ...properties });
  target.dispatchEvent(event);
  return event;
}

function timeline() {
  const element = Object.assign(new EventTarget(), { scrollLeft: 200, getBoundingClientRect: () => ({ left: 100, width: 800 }) });
  const positions = [];
  const dispose = loadZoom().bindTimelineZoom({ element, zoom: 2, onZoom: value => positions.push(value) });
  return { wheel: properties => dispatchWheel(element, properties), positions, dispose };
}

test('Ctrl wheel outside the timeline cancels page zoom but leaves plain scrolling alone', () => {
  const page = new EventTarget();
  const dispose = loadZoom().bindPageZoomPrevention(page);
  assert.equal(dispatchWheel(page, { ctrlKey: true }).defaultPrevented, true);
  assert.equal(dispatchWheel(page, { metaKey: true }).defaultPrevented, false);
  assert.equal(dispatchWheel(page).defaultPrevented, false);
  dispose();
  assert.equal(dispatchWheel(page, { ctrlKey: true }).defaultPrevented, false);
});

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

test('Ctrl wheel reaches 128× and stops at that limit', () => {
  const { wheel, positions } = timeline();
  for (let turn = 0; turn < 8; turn++) wheel({ ctrlKey: true });
  assert.deepEqual(positions.map(position => position.zoom), [4, 8, 16, 32, 64, 128]);
});

test('minimum zoom fits the timeline viewport with no horizontal overflow', () => {
  const { wheel, positions } = timeline();
  wheel({ ctrlKey: true, deltaY: 100 });
  assert.equal(positions.at(-1).zoom, 1);
  assert.equal(positions.at(-1).scrollLeft, 0);
  assert.equal(loadLayout().timelineWidth(800, positions.at(-1).zoom), 800);
});

test('jumping to a song reveals its start without changing an already visible view', () => {
  const { revealTimelinePosition } = loadLayout();
  const viewport = { width: 800, scrollLeft: 200, scrollWidth: 3200 };
  assert.equal(revealTimelinePosition(1600, viewport), 1576);
  assert.equal(revealTimelinePosition(600, viewport), 200);
  assert.equal(revealTimelinePosition(50, viewport), 26);
  assert.equal(revealTimelinePosition(10, viewport), 0);
  assert.equal(revealTimelinePosition(3190, viewport), 2400);
});

test('Meta wheel zooms out and cleanup removes interception', () => {
  const { wheel, positions, dispose } = timeline();
  assert.equal(wheel({ metaKey: true, deltaY: 100 }).defaultPrevented, true);
  assert.equal(positions[0].zoom, 1);
  assert.equal(positions[0].scrollLeft, 0);
  dispose();
  assert.equal(wheel({ ctrlKey: true }).defaultPrevented, false);
});
