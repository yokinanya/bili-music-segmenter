import assert from 'node:assert/strict';
import test from 'node:test';
import { selectSongRange } from '../src/lib/rangeSelection.ts';

const ids = ['a', 'b', 'c', 'd'];
test('shift selects an inclusive range in both directions', () => {
  assert.deepEqual(selectSongRange({ ids, anchor: 'b', target: 'd' }), ['b', 'c', 'd']);
  assert.deepEqual(selectSongRange({ ids, anchor: 'd', target: 'b' }), ['b', 'c', 'd']);
});
test('a deleted or absent anchor starts selection at the clicked song', () => {
  assert.deepEqual(selectSongRange({ ids, anchor: null, target: 'c' }), ['c']);
  assert.deepEqual(selectSongRange({ ids, anchor: 'removed', target: 'b' }), ['b']);
});
