import assert from 'node:assert/strict';
import test from 'node:test';
import { parseNavigation, serializeNavigation, PAGES } from '../src/lib/navigation.ts';

test('removed pages fall back to the workstation instead of rendering nothing', () => {
  const state = parseNavigation('page=历史&history=abc123');
  assert.equal(state.page, '工作台');
  assert.equal(state.history, undefined);
});

test('only sidebar pages survive a round trip', () => {
  for (const page of PAGES) {
    const round = parseNavigation(serializeNavigation({ page, source: '本地文件', view: '导入与设置' }));
    assert.equal(round.page, page);
  }
});

test('serializing drops defaults and unrelated keys', () => {
  const query = serializeNavigation({ page: '链接下载', usage: 'job-1' });
  assert.equal(query, 'page=' + encodeURIComponent('链接下载') + '&usage=job-1');
});
