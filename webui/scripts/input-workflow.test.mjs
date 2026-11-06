import assert from 'node:assert/strict';
import { test } from 'node:test';
import { reselectDraft } from '../src/lib/reselectDraft.ts';
import { validateParameters } from '../src/lib/parameterValidation.ts';

test('reselect keeps the original draft identity and source', () => {
  const source = { id: 'source', name: 'song.mp4', size_bytes: 4, state: 'failed', sha256: '', error: null };
  const original = { key: 'draft', name: source.name, size: 4, sent: 2, state: 'failed', source };
  const file = new File(['song'], source.name);
  const result = reselectDraft([original], 'draft', file);
  assert.equal(result.key, original.key);
  assert.equal(result.source, source);
  assert.equal(result.file, file);
  assert.equal(result.state, 'pending');
  assert.equal(original.sent, 2);
});

test('reselect rejects mismatched names, sizes and missing drafts', () => {
  const original = { key: 'draft', name: 'song.mp4', size: 4, sent: 0, state: 'pending' };
  assert.throws(() => reselectDraft([original], 'draft', new File(['song'], 'other.mp4')), /不匹配/);
  assert.throws(() => reselectDraft([original], 'draft', new File(['longer'], 'song.mp4')), /不匹配/);
  assert.throws(() => reselectDraft([], 'draft', new File(['song'], 'song.mp4')), /已被移除/);
});

test('validation checks Material hosts, reports errors and focuses the first invalid field', () => {
  let focused = false, reported = 0;
  const invalid = { disabled: false, checkValidity: () => false, parentElement: null,
    reportValidity: () => { reported++; return false; }, focus: () => { focused = true; } };
  const disabled = { disabled: true, checkValidity: () => { throw new Error('disabled input checked'); } };
  const root = { querySelectorAll: () => [invalid, disabled] };
  const frame = globalThis.requestAnimationFrame;
  globalThis.requestAnimationFrame = (callback) => { callback(0); return 0; };
  try {
    assert.equal(validateParameters(root), false);
    assert.equal(reported, 1);
    assert.equal(focused, true);
    assert.equal(validateParameters({ querySelectorAll: () => [] }), true);
    const inactive = { ...invalid, parentElement: { hidden: true, classList: { contains: () => false } },
      checkValidity: () => { throw new Error('inactive pane checked'); } };
    assert.equal(validateParameters({ querySelectorAll: () => [inactive] }), true);
  } finally { globalThis.requestAnimationFrame = frame; }
});

