import assert from 'node:assert/strict';
import { test } from 'node:test';
import { readClipEdit } from '../src/lib/clipEditStream.ts';

const HEADERS = { 'Content-Type': 'application/x-ndjson' };
const progress = { stage: 'encoding', completed_seconds: 12.5, total_seconds: 30, elapsed_seconds: 2 };
const success = { stage: 'succeeded', clip: { id: 'clip', title: '修改后的歌名' } };

function response(events, blockSize = 7) {
  const bytes = new TextEncoder().encode(events.map(event => JSON.stringify(event)).join('\n') + '\n');
  return new Response(new ReadableStream({ start(controller) {
    for (let offset = 0; offset < bytes.length; offset += blockSize) controller.enqueue(bytes.slice(offset, offset + blockSize));
    controller.close();
  } }), { headers: HEADERS });
}

test('reads measured progress and UTF-8 result across arbitrary stream boundaries', async () => {
  const updates = [];
  const result = await readClipEdit(response([progress, success], 1), value => updates.push(value));
  assert.deepEqual(updates, [progress]);
  assert.equal(result.clip.title, '修改后的歌名');
});

test('delivers progress before the export response completes', async () => {
  let controller;
  const stream = new ReadableStream({ start(value) { controller = value; } });
  const updates = [];
  const promise = readClipEdit(new Response(stream, { headers: HEADERS }), value => updates.push(value));
  const encoder = new TextEncoder();
  controller.enqueue(encoder.encode(JSON.stringify(progress) + '\n'));
  await new Promise(resolve => setImmediate(resolve));
  assert.deepEqual(updates, [progress]);
  controller.enqueue(encoder.encode(JSON.stringify(success) + '\n'));
  controller.close();
  assert.equal((await promise).clip.id, 'clip');
});

test('reports export failure after partial progress', async () => {
  const updates = [];
  await assert.rejects(readClipEdit(response([progress, { stage: 'failed', error: '编码失败详情' }]), value => updates.push(value)), /编码失败详情/);
  assert.equal(updates.length, 1);
});

test('a closed connection without completion never reports success', async () => {
  await assert.rejects(readClipEdit(response([progress]), () => {}), /未收到完成结果/);
});

test('rejects invalid measured progress and unexpected records after success', async () => {
  await assert.rejects(readClipEdit(response([{ ...progress, completed_seconds: -1 }]), () => {}), /数值无效/);
  await assert.rejects(readClipEdit(response([success, progress]), () => {}), /额外记录/);
});

test('reports HTTP errors and unsupported stream responses', async () => {
  const error = new Response(JSON.stringify({ error: '访问令牌无效' }), { status: 403 });
  await assert.rejects(readClipEdit(error, () => {}), /访问令牌无效/);
  await assert.rejects(readClipEdit(Response.json({ clip: { id: 'old' } }), () => {}), /未返回导出进度/);
});
