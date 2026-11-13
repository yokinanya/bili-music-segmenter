import assert from 'node:assert/strict';
import { test } from 'node:test';
import { titleCandidates } from '../src/lib/titleCandidates.ts';

test('matching providers produce one candidate with the chosen title', () => {
  const rows = titleCandidates({
    shazam: { status: 'matched', title: '痴心絕對', artist: 'Sam Lee' },
    netease: { status: 'matched', title: '痴心绝对', artist: '李圣杰' },
  }, { status: 'matched' });
  assert.equal(rows.length, 1);
  assert.equal(rows[0].title, '痴心绝对');
  assert.deepEqual(rows[0].sources, ['Shazam', '网易云']);
});

test('conflicting providers keep every distinct title for manual choice', () => {
  const rows = titleCandidates({
    shazam: { status: 'matched', title: '青花', artist: '周传雄' },
    netease: { status: 'matched', title: '别的歌', artist: '别人' },
  }, { status: 'conflict' });
  assert.deepEqual(rows.map((row) => row.title), ['青花', '别的歌']);
});

test('same title from both providers is not offered twice even when artists differ', () => {
  const rows = titleCandidates({
    shazam: { status: 'matched', title: '唯一', artist: '甲' },
    netease: { status: 'matched', title: '唯一', artist: '乙' },
  }, { status: 'conflict' });
  assert.equal(rows.length, 1);
  assert.equal(rows[0].title, '唯一');
});

test('missing and malformed recognition yields no candidates', () => {
  for (const value of [null, undefined, {}, [], 'legacy', 3]) assert.deepEqual(titleCandidates(value, value), []);
});
