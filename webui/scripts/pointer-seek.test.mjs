import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { createRequire } from 'node:module';
import test from 'node:test';
import { runInNewContext } from 'node:vm';

const require = createRequire(import.meta.url);
const { transformSync } = require('next/dist/build/swc');
const source = readFileSync(new URL('../src/lib/usePointerSeek.ts', import.meta.url), 'utf8');
const { code } = transformSync(source, { jsc: { parser: { syntax: 'typescript' } }, module: { type: 'commonjs' } });
const hook = { exports: {} };
runInNewContext(code, {
  exports: hook.exports, module: hook,
  require: name => {
    assert.equal(name, 'react');
    return { useRef: current => ({ current }) };
  },
});

function interaction(enabled = true) {
  const positions = [], lifecycle = [], captures = new Set();
  const target = {
    setPointerCapture: id => captures.add(id),
    hasPointerCapture: id => captures.has(id),
    releasePointerCapture: id => captures.delete(id),
  };
  const handlers = hook.exports.usePointerSeek({
    enabled, onSeek: x => positions.push(x),
    onStart: () => lifecycle.push('start'), onEnd: () => lifecycle.push('end'),
  });
  const event = (clientX, pointerId = 1) => ({
    clientX, pointerId, button: 0, currentTarget: target, preventDefault() {},
  });
  return { handlers, event, positions, lifecycle, captures };
}

test('hovering without a press never changes playback position', () => {
  const { handlers, event, positions } = interaction();
  handlers.onPointerMove(event(300));
  handlers.onPointerUp(event(400));
  assert.deepEqual(positions, []);
});

test('drag seeks continuously and includes the final release position', () => {
  const { handlers, event, positions, lifecycle, captures } = interaction();
  handlers.onPointerDown(event(100));
  handlers.onPointerMove(event(300));
  handlers.onPointerUp(event(450));
  handlers.onLostPointerCapture(event(450));
  handlers.onPointerMove(event(600));
  assert.deepEqual(positions, [100, 300, 450]);
  assert.deepEqual(lifecycle, ['start', 'end']);
  assert.equal(captures.size, 0);
});

test('cancel ends a drag without seeking to the cancellation coordinate', () => {
  const { handlers, event, positions, lifecycle } = interaction();
  handlers.onPointerDown(event(100));
  handlers.onPointerCancel(event(900));
  handlers.onPointerMove(event(600));
  assert.deepEqual(positions, [100]);
  assert.deepEqual(lifecycle, ['start', 'end']);
});

test('a different pointer cannot move or finish the active drag', () => {
  const { handlers, event, positions, lifecycle } = interaction();
  handlers.onPointerDown(event(100));
  handlers.onPointerDown(event(200, 2));
  handlers.onPointerMove(event(300, 2));
  handlers.onPointerUp(event(400, 2));
  handlers.onPointerMove(event(500));
  handlers.onPointerUp(event(600));
  assert.deepEqual(positions, [100, 500, 600]);
  assert.deepEqual(lifecycle, ['start', 'end']);
});

test('an unavailable media track cannot start seeking', () => {
  const { handlers, event, positions, lifecycle } = interaction(false);
  handlers.onPointerDown(event(100));
  handlers.onPointerMove(event(300));
  handlers.onPointerUp(event(400));
  assert.deepEqual(positions, []);
  assert.deepEqual(lifecycle, []);
});
