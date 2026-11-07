import assert from 'node:assert/strict';
import { test } from 'node:test';
import { clipEvidence } from '../src/lib/clipEvidence.ts';

test('old evidence shows readable providers and model rationale', () => {
  const rows = clipEvidence({ shazam: { status: 'no_match' }, netease: { status: 'error', error: '失败详情' } }, {
    status: 'audio_verified', audio: { data: { confidence: 0.9, rationale: '听到清晰演唱', lyrics_evidence: '实听歌词' } },
  });
  assert(rows.some(row => row.text === '未匹配'));
  assert(rows.some(row => row.text.includes('失败详情')));
  assert(rows.some(row => row.text === '90%'));
  assert(rows.some(row => row.text === '听到清晰演唱'));
});

test('QQ and manual evidence are readable without raw JSON', () => {
  const rows = clipEvidence({}, { status: 'manual', qqmusic: { status: 'matched', query: '实听歌词', title: '青花',
    artist: '周传雄', mid: '002MFDAV3rPFlo', candidates: [{ title: '青花', artist: '周传雄' }] },
    manual: { reason: '两段歌词交叉核对' } });
  assert(rows.some(row => row.text === '人工确认'));
  assert(rows.some(row => row.text === '两段歌词交叉核对'));
  assert(rows.some(row => row.text.includes('QQ') === false && row.text.includes('青花')));
});

test('empty and malformed old evidence renders without errors', () => {
  for (const value of [null, undefined, [], 'legacy', 2]) assert.equal(clipEvidence(value, value)[0].text, '未记录');
});
