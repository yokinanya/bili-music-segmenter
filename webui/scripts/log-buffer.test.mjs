import assert from 'node:assert/strict';
import test from 'node:test';
import { appendLog, emptyLog, findLog, PAGE_ROWS, ROW_CHARACTERS, readLogSnapshot, rowAt } from '../src/components/logBuffer.ts';

test('long Unicode logs retain their complete content across display pages', () => {
  const text = `${'中文😀'.repeat(ROW_CHARACTERS)}\n`.repeat(PAGE_ROWS);
  const buffer = appendLog(emptyLog(), text);
  assert.equal(buffer.segments.join(''), text);
  assert.equal(buffer.length, text.length);
  assert.ok(buffer.rows.length > PAGE_ROWS);
  assert.equal(buffer.rows.some(row => /[\uD800-\uDBFF]$/.test(row.text)), false);
});

test('search covers chunk and row boundaries and locates the history page', () => {
  const prefix = `${'first\n'.repeat(PAGE_ROWS)}${'a'.repeat(ROW_CHARACTERS - 2)}`;
  const initial = appendLog(emptyLog(), `${prefix}中`);
  const buffer = appendLog(initial, '文😀error\nlast');
  const [match] = findLog(buffer, '中文😀error');
  assert.equal(match, prefix.length);
  assert.equal(Math.floor(rowAt(buffer.rows, match) / PAGE_ROWS), 1);
  assert.equal(findLog(buffer, 'ERROR').length, 0);
  assert.equal(initial.segments.join(''), `${prefix}中`);
});

test('export reads through a nonempty terminal chunk to the actual end', async () => {
  const chunks = [
    { text: '中文\n', offset: 7, complete: true },
    { text: 'last\n', offset: 12, complete: true },
    { text: '', offset: 12, complete: true },
  ];
  const offsets = [];
  const segments = await readLogSnapshot(async offset => {
    offsets.push(offset);
    return chunks[offsets.length - 1];
  });
  assert.deepEqual(offsets, [0, 7, 12]);
  assert.equal(segments.join(''), '中文\nlast\n');
});

test('export exposes read failures and offsets that do not advance', async () => {
  await assert.rejects(readLogSnapshot(async () => {
    throw new Error('日志连接断开');
  }), /日志连接断开/);
  await assert.rejects(readLogSnapshot(async () => ({
    text: 'unread', offset: 0, complete: false,
  })), /日志读取位置未前进/);
});
