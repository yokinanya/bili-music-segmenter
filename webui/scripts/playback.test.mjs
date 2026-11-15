import assert from 'node:assert/strict';
import test from 'node:test';
import { isInterruption, progressFraction, scrubFromPointer, scrubTime } from '../src/lib/playback.ts';

test('scrubbing clamps to the clip instead of wrapping or overshooting', () => {
  assert.equal(scrubTime(-5, 120), 0);
  assert.equal(scrubTime(121, 120), 120);
  assert.equal(scrubTime(42.5, 120), 42.5);
  assert.equal(scrubTime(10, 0), 0);
  assert.equal(scrubTime(Number.NaN, 120), 0);
});

test('a duration that media metadata has not provided yet never throws', () => {
  // video.duration is NaN before metadata, and a missing project supplies null.
  assert.equal(scrubTime(10, Number.NaN), 0);
  assert.equal(scrubTime(10, null), 0);
  assert.equal(scrubTime(10, undefined), 0);
  assert.equal(progressFraction(10, Number.NaN), 0);
});

test('pointer position maps to track time across the full width', () => {
  const rect = { left: 100, width: 800 };
  assert.equal(scrubFromPointer(100, rect, 80), 0);
  assert.equal(scrubFromPointer(500, rect, 80), 40);
  assert.equal(scrubFromPointer(900, rect, 80), 80);
  assert.equal(scrubFromPointer(950, rect, 80), 80);
  assert.equal(scrubFromPointer(500, { left: 0, width: 0 }, 80), 0);
});

test('progress stays within 0..1 so the handle never leaves the bar', () => {
  assert.equal(progressFraction(30, 120), 0.25);
  assert.equal(progressFraction(-1, 120), 0);
  assert.equal(progressFraction(200, 120), 1);
  assert.equal(progressFraction(10, 0), 0);
});

test('only an aborted play request is treated as an interruption', () => {
  assert.equal(isInterruption(new DOMException('interrupted', 'AbortError')), true);
  assert.equal(isInterruption(new DOMException('blocked', 'NotAllowedError')), false);
  assert.equal(isInterruption(new Error('boom')), false);
});
