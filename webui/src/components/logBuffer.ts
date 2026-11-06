import type { LogChunk } from '@/lib/types';

export const ROW_CHARACTERS = 240;
export const PAGE_ROWS = 200;
export interface LogRow { readonly text: string; readonly start: number }
export interface LogBuffer {
  readonly segments: readonly string[];
  readonly rows: readonly LogRow[];
  readonly length: number;
}
export const emptyLog = (): LogBuffer => ({ segments: [], rows: [{ text: '', start: 0 }], length: 0 });

export function appendLog(buffer: LogBuffer, text: string): LogBuffer {
  if (!text) return buffer;
  const rows = buffer.rows.slice(0, -1);
  let row = buffer.rows[buffer.rows.length - 1];
  let position = buffer.length;
  for (const character of text) {
    if (character === '\n') {
      rows.push(row);
      row = { text: '', start: position + 1 };
    } else {
      if (row.text.length >= ROW_CHARACTERS) {
        rows.push(row);
        row = { text: '', start: position };
      }
      row = { ...row, text: row.text + character };
    }
    position += character.length;
  }
  return { segments: [...buffer.segments, text], rows: [...rows, row], length: position };
}

export function findLog(buffer: LogBuffer, keyword: string): readonly number[] {
  if (!keyword) return [];
  const prefix = Array<number>(keyword.length).fill(0);
  for (let i = 1, matched = 0; i < keyword.length; i++) {
    while (matched && keyword[i] !== keyword[matched]) matched = prefix[matched - 1];
    if (keyword[i] === keyword[matched]) matched++;
    prefix[i] = matched;
  }
  const matches: number[] = [];
  let matched = 0, position = 0;
  for (const segment of buffer.segments) {
    for (let i = 0; i < segment.length; i++, position++) {
      while (matched && segment[i] !== keyword[matched]) matched = prefix[matched - 1];
      if (segment[i] === keyword[matched]) matched++;
      if (matched !== keyword.length) continue;
      matches.push(position - keyword.length + 1);
      matched = prefix[matched - 1];
    }
  }
  return matches;
}

export function rowAt(rows: readonly LogRow[], offset: number): number {
  let low = 0, high = rows.length;
  while (low + 1 < high) {
    const middle = Math.floor((low + high) / 2);
    if (rows[middle].start <= offset) low = middle;
    else high = middle;
  }
  return low;
}

export type ReadLog = (offset: number) => Promise<LogChunk>;
export async function readLogSnapshot(read: ReadLog): Promise<string[]> {
  const segments: string[] = [];
  let offset = 0;
  while (true) {
    const chunk = await read(offset);
    if (!chunk.text) return segments;
    if (chunk.offset <= offset) throw new Error('日志读取位置未前进，无法读取完整日志');
    segments.push(chunk.text);
    offset = chunk.offset;
  }
}
