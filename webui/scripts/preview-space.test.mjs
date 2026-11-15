import assert from 'node:assert/strict';
import test from 'node:test';
import { previewSpaceAction } from '../src/lib/previewSpace.ts';

test('space on micro-adjustment controls toggles playback, not the focused button', () => {
  assert.equal(previewSpaceAction({ editing: false, button: true, adjustment: true, blocked: false }), 'playback');
});
test('inputs, modal dialogs and ordinary buttons retain native space behavior', () => {
  assert.equal(previewSpaceAction({ editing: true, button: false, adjustment: false, blocked: false }), 'native');
  assert.equal(previewSpaceAction({ editing: false, button: true, adjustment: true, blocked: true }), 'native');
  assert.equal(previewSpaceAction({ editing: false, button: true, adjustment: false, blocked: false }), 'native');
});
test('space on the editor canvas toggles playback', () => {
  assert.equal(previewSpaceAction({ editing: false, button: false, adjustment: false, blocked: false }), 'playback');
});
