import assert from 'node:assert/strict';
import test from 'node:test';
import { nudgeBoundary } from '../src/lib/boundaryNudge.ts';

const clip = { id: 'one', start_seconds: 10.2, end_seconds: 20, title: 'Song', artist: '', name: 'Song.mp4' };
test('nudging either boundary preserves precision and the other boundary', () => {
  assert.equal(nudgeBoundary(clip, { edge: 'start_seconds', delta: -0.1, duration: 30 }).start_seconds, 10.1);
  assert.equal(nudgeBoundary(clip, { edge: 'end_seconds', delta: 0.01, duration: 30 }).end_seconds, 20.01);
  assert.equal(clip.start_seconds, 10.2);
});
test('nudges cannot leave source bounds or cross the opposite boundary', () => {
  assert.throws(() => nudgeBoundary(clip, { edge: 'start_seconds', delta: -11, duration: 30 }), /边界/);
  assert.throws(() => nudgeBoundary(clip, { edge: 'start_seconds', delta: 9.8, duration: 30 }), /边界/);
  assert.throws(() => nudgeBoundary(clip, { edge: 'end_seconds', delta: 11, duration: 30 }), /边界/);
});
