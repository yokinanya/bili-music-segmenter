import assert from 'node:assert/strict';
import { test } from 'node:test';
import { summarizeBatch, summarizeProgress } from '../src/lib/progressSummary.ts';

const STARTED_AT = '2026-11-07T10:00:00+08:00';
const job = { state: 'running', attempt: 1, error: null, cleanup_error: null };

function step(changes = {}) {
  return {
    id: 'scan', parent_id: null, label: '分块扫描', state: 'running',
    completed: 0, total: null, unit: null, attempt: 1, sequence: 1,
    started_at: STARTED_AT, finished_at: null, error: null, ...changes,
  };
}

function item(changes = {}) {
  return {
    id: 'video', upload_id: 'source', media: '直播录像.mp4', state: 'running',
    steps: [], error: null, started_at: STARTED_AT, finished_at: null, ...changes,
  };
}

function summarize(steps, changes = {}, jobChanges = {}) {
  return summarizeProgress({ item: item({ steps, ...changes }), job: { ...job, ...jobChanges } });
}

test('selects an active leaf even when its parent has a newer event', () => {
  const result = summarize([
    step({ completed: 3, total: 10, unit: '项', sequence: 100 }),
    step({ id: 'scan/4', parent_id: 'scan', label: '扫描分块 4', sequence: 2 }),
    step({ id: 'model', parent_id: 'scan/4', label: '音频模型', sequence: 3 }),
  ]);
  assert.equal(result.current.step.id, 'model');
  assert.equal(result.current.context, '分块扫描 · 扫描分块 4');
  assert.equal(result.parallelCount, 0);
  assert.deepEqual(result.measurement, { label: '分块扫描', completed: 3, total: 10, unit: '项' });
  assert.equal(result.details.length, 3);
});

test('selects the newest concurrent leaf and excludes aggregate counters', () => {
  const result = summarize([
    step({ id: 'prepare', label: '候选处理', total: 5, sequence: 500 }),
    step({ id: 'finalize', label: '最终复核与导出', total: 5, sequence: 501 }),
    step({ id: 'candidate/1', label: '候选 1', sequence: 2 }),
    step({ id: 'candidate/2', label: '候选 2', sequence: 4 }),
    step({ id: 'candidate/3', label: '候选 3', sequence: 3 }),
  ]);
  assert.equal(result.current.step.id, 'candidate/2');
  assert.equal(result.parallelCount, 2);
  assert.equal(result.details[0].measurement.total, 5);
});

test('aggregate counters alone do not announce work that has not started', () => {
  const result = summarize([step({ id: 'prepare' }), step({ id: 'finalize' })]);
  assert.equal(result.current, null);
  assert.equal(result.parallelCount, 0);
  assert.equal(result.measurement, null);
});

test('suppresses active ancestors through an inactive intermediate step', () => {
  const result = summarize([
    step({ sequence: 100 }),
    step({ id: 'middle', parent_id: 'scan', state: 'succeeded' }),
    step({ id: 'leaf', parent_id: 'middle', sequence: 3 }),
  ]);
  assert.equal(result.current.step.id, 'leaf');
  assert.equal(result.parallelCount, 0);
});

test('breaks equal sequence ties using the later record for download events', () => {
  const result = summarize([
    step({ id: 'download/video', label: '下载视频轨', sequence: 0 }),
    step({ id: 'download/audio', label: '下载音频轨', sequence: 0, completed: 40, total: 100, unit: '字节' }),
  ]);
  assert.equal(result.current.step.id, 'download/audio');
  assert.equal(result.parallelCount, 1);
  assert.equal(result.measurement.completed, 40);
  assert.equal(result.measurement.unit, '字节');
});

test('preserves waiting and retrying states and their full messages', () => {
  for (const state of ['waiting', 'retrying']) {
    const message = '请求返回的边界不合法\n需要重新复核';
    const result = summarize([step({ state, message, waiting_seconds: 12 })]);
    assert.equal(result.current.step.state, state);
    assert.equal(result.current.step.message, message);
    assert.equal(result.current.step.waiting_seconds, 12);
    assert.equal(result.measurement, null);
  }
});

test('prefers a leaf measurement over a measured ancestor', () => {
  const result = summarize([
    step({ completed: 3, total: 10, unit: '项' }),
    step({ id: 'ffmpeg', parent_id: 'scan', label: '提取音频', completed: 25, total: 60, unit: '秒', sequence: 2 }),
  ]);
  assert.equal(result.measurement.label, '提取音频');
  assert.equal(result.measurement.completed, 25);
  assert.equal(result.measurement.total, 60);
  assert.equal(result.measurement.unit, '秒');
});

test('uses the closest measured ancestor and treats zero totals as unknown', () => {
  const result = summarize([
    step({ total: 10 }),
    step({ id: 'chunk', parent_id: 'scan', label: '扫描分块 1', total: 60, unit: '秒', sequence: 2 }),
    step({ id: 'model', parent_id: 'chunk', total: 0, sequence: 3 }),
  ]);
  assert.equal(result.measurement.label, '扫描分块 1');
  assert.equal(result.measurement.total, 60);
  assert.equal(summarize([step({ total: 0 })]).measurement, null);
});

test('merge steps with unknown totals remain indeterminate', () => {
  const result = summarize([step({ id: 'merge/ffmpeg', label: '合并与封装', sequence: 0 })]);
  assert.equal(result.current.step.label, '合并与封装');
  assert.equal(result.running, true);
  assert.equal(result.measurement, null);
});

test('terminal video states suppress stale active steps and uploads', () => {
  for (const state of ['succeeded', 'failed', 'cancelled', 'interrupted', 'cleanup_pending']) {
    const result = summarize([step()], {
      state,
      upload: { uploads: [{ key: 'audio.wav', state: 'uploading', transferred_bytes: 5, total_bytes: 10 }] },
    });
    assert.equal(result.state, state);
    assert.equal(result.running, false);
    assert.equal(result.current, null);
    assert.equal(result.measurement, null);
    assert.equal(result.uploading, null);
    assert.equal(result.details.length, 1);
    assert.equal(result.uploads.length, 1);
  }
});

test('a terminal job overrides an unfinished selected video', () => {
  for (const state of ['failed', 'cancelled', 'interrupted', 'cleanup_pending']) {
    const result = summarize([step()], {}, { state });
    assert.equal(result.state, state);
    assert.equal(result.running, false);
    assert.equal(result.unprocessed, false);
    assert.equal(result.current, null);
  }
  assert.equal(summarize([], { state: 'queued' }, { state: 'failed' }).unprocessed, true);
});

test('preserves the final state of a completed video in an unfinished batch', () => {
  const result = summarize([step({ state: 'succeeded' })], { state: 'succeeded' }, { state: 'failed' });
  assert.equal(result.state, 'succeeded');
  assert.equal(result.unprocessed, false);
});

test('empty current and historical records expose their real state', () => {
  for (const state of ['queued', 'running', 'succeeded', 'failed', 'cancelled', 'interrupted']) {
    const result = summarize([], { state }, { state });
    assert.equal(result.state, state);
    assert.equal(result.details.length, 0);
    assert.equal(result.current, null);
    assert.equal(result.running, state === 'running');
  }
});

test('resume ignores older active steps while retaining reused and skipped details', () => {
  const result = summarize([
    step({ id: 'old', attempt: 1, sequence: 999 }),
    step({ id: 'cached', state: 'reused', attempt: 2 }),
    step({ id: 'skip', state: 'skipped', attempt: 2 }),
    step({ id: 'current', attempt: 2, sequence: 3 }),
  ], {}, { attempt: 2 });
  assert.equal(result.current.step.id, 'current');
  assert.equal(result.parallelCount, 0);
  assert.deepEqual(result.details.map(({ step: value }) => value.state), ['running', 'reused', 'skipped', 'running']);
});

test('groups duplicate errors across task, video and nested steps with every source', () => {
  const message = '模型请求失败\n上游响应 503';
  const result = summarize([
    step({ state: 'failed', error: message }),
    step({ id: 'model', parent_id: 'scan', label: '音频模型', state: 'failed', error: message }),
  ], { state: 'failed', error: message }, { state: 'failed', error: message, cleanup_error: '缓存清理失败' });
  assert.deepEqual(result.issues, [
    { message, sources: ['任务', '直播录像.mp4', '分块扫描', '分块扫描 · 音频模型'] },
    { message: '缓存清理失败', sources: ['任务清理'] },
  ]);
});

test('exposes failed steps without recorded error text', () => {
  const result = summarize([step({ state: 'failed' })], { state: 'failed' }, { state: 'failed' });
  assert.deepEqual(result.issues, [{ message: '步骤执行失败，尚无错误详情', sources: ['分块扫描'] }]);
});

test('aggregates only uploading S3 objects using their real bytes', () => {
  const uploads = [
    { key: 'first.wav', state: 'uploading', transferred_bytes: 20, total_bytes: 100 },
    { key: 'second.wav', state: 'uploading', transferred_bytes: 30, total_bytes: 200 },
    { key: 'done.wav', state: 'completed', transferred_bytes: 900, total_bytes: 900 },
  ];
  const result = summarize([], { upload: { uploads } });
  assert.deepEqual(result.uploading, { count: 2, completed: 50, total: 300 });
  assert.deepEqual(result.measurement, { label: 'S3 上传', completed: 50, total: 300, unit: '字节' });
  assert.equal(result.uploads, uploads);
});

test('S3 aggregate total is unknown when any active upload has an unknown total', () => {
  const result = summarize([], { upload: { uploads: [
    { key: 'known.wav', state: 'uploading', transferred_bytes: 20, total_bytes: 100 },
    { key: 'unknown.wav', state: 'uploading', transferred_bytes: 30, total_bytes: 0 },
  ] } });
  assert.deepEqual(result.uploading, { count: 2, completed: 50, total: null });
  assert.equal(result.measurement, null);
});

test('measured work retains priority over simultaneous S3 uploads', () => {
  const result = summarize([step({ completed: 2, total: 10, unit: '项' })], { upload: { uploads: [
    { key: 'audio.wav', state: 'uploading', transferred_bytes: 20, total_bytes: 100 },
  ] } });
  assert.equal(result.measurement.unit, '项');
  assert.equal(result.uploading.completed, 20);
});

test('S3 failures stay visible and retain all failed object keys', () => {
  const result = summarize([], { upload: { uploads: [
    { key: 'first.wav', state: 'failed', transferred_bytes: 10, total_bytes: 100 },
    { key: 'second.wav', state: 'failed', transferred_bytes: 20, total_bytes: 100 },
  ] } });
  assert.deepEqual(result.issues, [{
    message: 'S3 上传失败', sources: ['S3 上传 · first.wav', 'S3 上传 · second.wav'],
  }]);
});

test('orphaned historical steps remain visible', () => {
  const result = summarize([step({ parent_id: 'missing' })]);
  assert.equal(result.current.step.id, 'scan');
  assert.equal(result.current.context, '');
  assert.equal(result.details.length, 1);
});

test('invalid cyclic step hierarchies report an explicit error', () => {
  assert.throws(() => summarize([
    step({ parent_id: 'child' }),
    step({ id: 'child', parent_id: 'scan' }),
  ]), /步骤层级存在循环/);
});

test('batch counts include ended videos and only nonzero exception totals', () => {
  const result = summarizeBatch([
    item({ state: 'succeeded' }), item({ state: 'failed' }), item({ state: 'running' }),
    item({ state: 'cancelled' }), item({ state: 'queued' }), item({ state: 'failed' }),
  ]);
  assert.deepEqual(result, { ended: 4, issues: [{ label: '失败', count: 2 }, { label: '已停止', count: 1 }] });
  assert.deepEqual(summarizeBatch([item({ state: 'succeeded' })]), { ended: 1, issues: [] });
  assert.deepEqual(summarizeBatch([]), { ended: 0, issues: [] });
});

test('derivation leaves frozen input records unchanged', () => {
  const steps = Object.freeze([Object.freeze(step())]);
  const video = Object.freeze(item({ steps }));
  const task = Object.freeze({ ...job });
  const before = JSON.stringify({ video, task });
  summarizeProgress({ item: video, job: task });
  assert.equal(JSON.stringify({ video, task }), before);
});
