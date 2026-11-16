import assert from 'node:assert/strict';
import test from 'node:test';
import { previewSpaceAction } from '../src/lib/previewSpace.ts';

test('space on micro-adjustment controls toggles playback, not the focused button', () => {
  assert.equal(previewSpaceAction({ editing: false, blocked: false }), 'playback');
});
test('only inputs and modal dialogs retain native space behavior', () => {
  assert.equal(previewSpaceAction({ editing: true, blocked: false }), 'native');
  assert.equal(previewSpaceAction({ editing: false, blocked: true }), 'native');
});
test('space on the editor canvas toggles playback', () => {
  assert.equal(previewSpaceAction({ editing: false, blocked: false }), 'playback');
});
