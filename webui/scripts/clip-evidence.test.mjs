import assert from 'node:assert/strict';
import { test } from 'node:test';
import { clipEvidence } from '../src/lib/clipEvidence.ts';

test('provider results and announcer hint stay readable without raw JSON', () => {
  const rows = clipEvidence({
    shazam: { status: 'no_match' },
    netease: { status: 'error', error: '失败详情' },
    announcer_hint: '接下来唱一首老歌',
  }, { status: 'conflict' });
  assert(rows.some((row) => row.text === '未匹配'));
  assert(rows.some((row) => row.text.includes('失败详情')));
  assert(rows.some((row) => row.label === '主播报幕' && row.text === '接下来唱一首老歌'));
  assert(rows.some((row) => row.text === '识曲结果不一致，请手动填写'));
});

test('manual edits remain visible', () => {
  const rows = clipEvidence({}, { status: 'manual', manual: { reason: '人工核对歌词' } });
  assert(rows.some((row) => row.text === '人工确认'));
  assert(rows.some((row) => row.text === '人工核对歌词'));
});

test('empty and malformed old evidence renders without errors', () => {
  for (const value of [null, undefined, [], 'legacy', 2]) assert.equal(clipEvidence(value, value)[0].text, '未记录');
});
