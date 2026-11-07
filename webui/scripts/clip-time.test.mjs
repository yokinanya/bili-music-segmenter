import assert from 'node:assert/strict';
import test from 'node:test';
import { mediaTime } from '../src/lib/format.ts';

test('song times use padded minutes and seconds', () => {
  assert.equal(mediaTime(0), '00:00');
  assert.equal(mediaTime(200), '03:20');
  assert.equal(mediaTime(465), '07:45');
});

test('song times support fractional boundaries and videos over one hour', () => {
  assert.equal(mediaTime(59.999), '00:59');
  assert.equal(mediaTime(3600), '1:00:00');
  assert.equal(mediaTime(7385.125), '2:03:05');
});
