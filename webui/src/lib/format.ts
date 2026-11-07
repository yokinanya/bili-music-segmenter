import type { ProgressStep } from './types';

const BYTE_BASE = 1024;
const BYTE_UNITS = ['B', 'KB', 'MB', 'GB'] as const;
const FRACTION_DIGITS = 1;
const PERCENT_SCALE = 100;
const SECONDS_PER_MINUTE = 60;
const MINUTES_PER_HOUR = 60;

export function mediaTime(seconds: number) {
  const whole = Math.floor(seconds);
  const minutes = Math.floor(whole / SECONDS_PER_MINUTE);
  const remainder = String(whole % SECONDS_PER_MINUTE).padStart(2, '0');
  if (minutes < MINUTES_PER_HOUR) return `${String(minutes).padStart(2, '0')}:${remainder}`;
  const hours = Math.floor(minutes / MINUTES_PER_HOUR);
  return `${hours}:${String(minutes % MINUTES_PER_HOUR).padStart(2, '0')}:${remainder}`;
}

export function bytes(value: number) {
  const index = Math.min(Math.floor(Math.log(Math.max(1, value)) / Math.log(BYTE_BASE)), BYTE_UNITS.length - 1);
  const size = (value / BYTE_BASE ** index).toFixed(index ? FRACTION_DIGITS : 0);
  return `${size} ${BYTE_UNITS[index]}`;
}

export function progressCounter({ completed, total, unit }: Readonly<Pick<ProgressStep, 'completed' | 'total' | 'unit'>>) {
  const hasTotal = total !== null && total > 0;
  const number = (value: number) => Number(value.toFixed(FRACTION_DIGITS));
  if (unit === '字节') {
    if (!hasTotal) return `${bytes(completed)} · 总量未知`;
    const percentage = number(completed / total * PERCENT_SCALE);
    return `${bytes(completed)} / ${bytes(total)} · ${percentage}%`;
  }
  if (!hasTotal) return '';
  return `${number(completed)} / ${number(total)}${unit ? ` ${unit}` : ''}`;
}

export function elapsed(start: string | null, end: string | null = null) { if (!start) return '—'; const seconds = Math.max(0, Math.round(((end ? Date.parse(end) : Date.now()) - Date.parse(start)) / 1000)); return `${Math.floor(seconds / 60)}分 ${seconds % 60}秒`; }
export const errorText = (error: unknown) => error instanceof Error ? error.message : String(error);
