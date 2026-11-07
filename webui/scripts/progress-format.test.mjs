import assert from 'node:assert/strict';
import { test } from 'node:test';
import { progressCounter } from '../src/lib/format.ts';

test('download sizes use readable units and include their percentage', () => {
  assert.equal(
    progressCounter({ completed: 268435456, total: 1073741824, unit: '字节' }),
    '256.0 MB / 1.0 GB · 25%',
  );
});

test('download percentages retain one decimal when needed', () => {
  assert.equal(
    progressCounter({ completed: 1024, total: 3072, unit: '字节' }),
    '1.0 KB / 3.0 KB · 33.3%',
  );
});

test('download counters show zero and completed transfers explicitly', () => {
  assert.equal(progressCounter({ completed: 0, total: 512, unit: '字节' }), '0 B / 512 B · 0%');
  assert.equal(progressCounter({ completed: 512, total: 512, unit: '字节' }), '512 B / 512 B · 100%');
});

test('unknown download totals preserve the transferred size without a percentage', () => {
  for (const total of [null, 0]) {
    assert.equal(progressCounter({ completed: 1536, total, unit: '字节' }), '1.5 KB · 总量未知');
    assert.equal(progressCounter({ completed: 0, total, unit: '字节' }), '0 B · 总量未知');
  }
});

test('download counters expose transferred bytes above the recorded total', () => {
  assert.equal(progressCounter({ completed: 2048, total: 1024, unit: '字节' }), '2.0 KB / 1.0 KB · 200%');
});

test('step counts retain their numeric units and fractional precision', () => {
  assert.equal(progressCounter({ completed: 2, total: 10, unit: '项' }), '2 / 10 项');
  assert.equal(progressCounter({ completed: 1.23, total: 4.56, unit: '秒' }), '1.2 / 4.6 秒');
  assert.equal(progressCounter({ completed: 2, total: 10, unit: null }), '2 / 10');
});

test('non-byte steps without a measured total keep an indeterminate count', () => {
  for (const total of [null, 0]) {
    assert.equal(progressCounter({ completed: 2, total, unit: '项' }), '');
    assert.equal(progressCounter({ completed: 0, total, unit: null }), '');
  }
});
