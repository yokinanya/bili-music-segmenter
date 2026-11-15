import assert from 'node:assert/strict';
import test from 'node:test';
import { selectionAtTime } from '../src/lib/playheadSelection.ts';

const clips = [
  { id: 'first', start_seconds: 10, end_seconds: 30 },
  { id: 'second', start_seconds: 20, end_seconds: 40 },
  { id: 'third', start_seconds: 40, end_seconds: 50 },
];
test('overlap retains current selection, otherwise chooses latest starting clip', () => {
  assert.deepEqual(selectionAtTime({ clips, selected: ['first'], time: 25 }), ['first']);
  assert.deepEqual(selectionAtTime({ clips, selected: [], time: 25 }), ['second']);
  assert.deepEqual(selectionAtTime({ clips, selected: ['first'], time: 35 }), ['second']);
});
test('explicit seeks use half-open bounds and gaps clear selection', () => {
  assert.deepEqual(selectionAtTime({ clips, selected: ['second'], time: 40 }), ['third']);
  assert.deepEqual(selectionAtTime({ clips, selected: ['first'], time: 5 }), []);
});
test('playback reaching selected endpoint retains its selection for automatic pause', () => {
  assert.deepEqual(selectionAtTime({ clips, selected: ['second'], time: 40, keepEndpoint: true }), ['second']);
});
test('manual multiselection remains until an explicit seek resumes following', () => {
  const selected = ['first', 'second'];
  assert.deepEqual(selectionAtTime({ clips, selected, time: 45, preserveSelection: true }), selected);
  assert.deepEqual(selectionAtTime({ clips, selected, time: 45 }), ['third']);
});
