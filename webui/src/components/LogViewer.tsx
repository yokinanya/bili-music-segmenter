'use client';
import { useCallback, useEffect, useRef, useState } from 'react';
import { api } from '@/lib/api';
import { errorText } from '@/lib/format';
import { Button } from './Material';
const POLL_MS = 1000;
export function LogViewer({ jobId, index }: { jobId: string; index: number }) {
  const [text, setText] = useState(''), [error, setError] = useState(''), [revision, setRevision] = useState(0);
  const [follow, setFollow] = useState(true);
  const box = useRef<HTMLPreElement>(null);
  const retry = useCallback(() => setRevision((value) => value + 1), []);
  useEffect(() => {
    let alive = true, offset = 0, timer: ReturnType<typeof setTimeout>;
    setText(''); setError('');
    const poll = async () => {
      try {
        const result = await api.log(jobId, index, offset);
        if (!alive) return;
        offset = result.offset; setText((value) => value + result.text); setError('');
        if (!result.complete) timer = setTimeout(poll, POLL_MS);
      } catch (cause) { if (alive) setError(errorText(cause)); }
    };
    void poll(); return () => { alive = false; clearTimeout(timer); };
  }, [jobId, index, revision]);
  useEffect(() => { if (follow && box.current) box.current.scrollTop = box.current.scrollHeight; }, [text, follow]);
  return <div className="log-wrap"><div className="section-head"><h3>执行日志</h3><Button variant="text" onClick={() => setFollow(!follow)}>{follow ? '暂停跟随' : '跟随最新'}</Button></div>
    {error && <div className="error">{error}<Button onClick={retry}>重新读取日志</Button></div>}
    <pre ref={box} className="log" tabIndex={0} aria-label="执行日志" onScroll={(event) => { const node = event.currentTarget; setFollow(node.scrollTop + node.clientHeight >= node.scrollHeight - 24); }}>{text || '等待进程输出…'}</pre>
  </div>;
}
