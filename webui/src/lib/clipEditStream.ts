import type { Clip, ClipEditProgress } from './types';

type EditEvent = ClipEditProgress | { stage: 'succeeded'; clip: Clip } | { stage: 'failed'; error: string };

function parseEvent(line: string): EditEvent {
  const event = JSON.parse(line);
  if (!event || typeof event !== 'object') throw new Error('导出进度格式无效');
  if (event.stage === 'failed' && typeof event.error === 'string') return event;
  if (event.stage === 'succeeded' && typeof event.clip?.id === 'string') return event;
  if (!['preparing', 'encoding', 'saving'].includes(event.stage)) throw new Error('导出状态无效');
  if (!Number.isFinite(event.completed_seconds) || event.completed_seconds < 0
    || !Number.isFinite(event.elapsed_seconds) || event.elapsed_seconds < 0
    || (event.total_seconds !== null && (!Number.isFinite(event.total_seconds) || event.total_seconds <= 0))) {
    throw new Error('导出进度数值无效');
  }
  return event;
}

async function* lines(body: ReadableStream<Uint8Array>) {
  const reader = body.getReader();
  const decoder = new TextDecoder();
  let pending = '';
  try {
    while (true) {
      const { done, value } = await reader.read();
      pending += decoder.decode(value, { stream: !done });
      const records = pending.split('\n');
      pending = records.pop()!;
      for (const line of records) if (line.trim()) yield line;
      if (done) break;
    }
    if (pending.trim()) yield pending;
  } finally {
    reader.releaseLock();
  }
}

export async function readClipEdit(response: Response, update: (value: ClipEditProgress) => void): Promise<{ clip: Clip }> {
  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.error ?? `保存失败（${response.status}）`);
  }
  if (!response.headers.get('Content-Type')?.startsWith('application/x-ndjson') || !response.body) {
    throw new Error('服务端未返回导出进度');
  }
  let clip: Clip | null = null;
  for await (const line of lines(response.body)) {
    if (clip) throw new Error('导出完成后返回了额外记录');
    const event = parseEvent(line);
    if (event.stage === 'failed') throw new Error(event.error);
    if (event.stage === 'succeeded') clip = event.clip;
    else update(event);
  }
  if (!clip) throw new Error('导出进度连接中断，未收到完成结果');
  return { clip };
}
