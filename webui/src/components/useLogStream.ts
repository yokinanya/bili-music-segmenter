import { useCallback, useEffect, useState } from 'react';
import { api } from '@/lib/api';
import { errorText } from '@/lib/format';
import { appendLog, emptyLog } from './logBuffer';

const POLL_MS = 1000;
export function useLogStream(jobId: string, index: number) {
  const [buffer, setBuffer] = useState(emptyLog);
  const [error, setError] = useState('');
  const [complete, setComplete] = useState(false);
  const [revision, setRevision] = useState(0);
  const retry = useCallback(() => setRevision(value => value + 1), []);
  useEffect(() => {
    let alive = true, offset = 0;
    let timer: ReturnType<typeof setTimeout> | undefined;
    setBuffer(emptyLog()); setError(''); setComplete(false);
    const poll = async () => {
      try {
        const chunk = await api.log(jobId, index, offset);
        if (!alive) return;
        if (chunk.text && chunk.offset <= offset) throw new Error('日志读取位置未前进');
        offset = chunk.offset;
        setBuffer(value => appendLog(value, chunk.text));
        setError('');
        if (!chunk.text && chunk.complete) { setComplete(true); return; }
        timer = setTimeout(poll, chunk.text ? 0 : POLL_MS);
      } catch (cause) { if (alive) setError(errorText(cause)); }
    };
    void poll();
    return () => { alive = false; clearTimeout(timer); };
  }, [jobId, index, revision]);
  return { buffer, error, complete, retry };
}
