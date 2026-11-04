'use client';
import { useCallback, useEffect, useState } from 'react';
import { api } from './api';
import { errorText } from './format';
import { isActive, type JobStatus } from './types';
const POLL_MS = 1000;
export function useTask(id: string | null, notify = false) {
  const [job, setJob] = useState<JobStatus | null>(null);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [revision, setRevision] = useState(0);
  const retry = useCallback(() => setRevision((value) => value + 1), []);
  useEffect(() => {
    let alive = true, timer: ReturnType<typeof setTimeout>;
    setError('');
    if (!id) return;
    const poll = async () => {
      try {
        const value = await api.job(id);
        if (!alive) return;
        setJob(value); setError('');
        if (isActive(value.state)) { timer = setTimeout(poll, POLL_MS); return; }
        if (!notify || value.state === 'cleanup_pending') return;
        const key = `bms-notified:${id}:${value.attempt}`;
        if (localStorage.getItem(key)) return;
        localStorage.setItem(key, '1');
        setNotice(`任务第 ${value.attempt} 次执行已结束，已生成 ${value.clips.length} 个片段`);
        if ('Notification' in window && Notification.permission === 'granted') new Notification('自动歌切', { body: `${value.clips.length} 个片段 · ${value.state}` });
      } catch (cause) { if (alive) setError(errorText(cause)); }
    };
    void poll();
    return () => { alive = false; clearTimeout(timer); };
  }, [id, revision, notify]);
  return { job: job?.id === id ? job : null, error, retry, notice, dismiss: () => setNotice('') };
}
