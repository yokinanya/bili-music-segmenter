'use client';
import { useCallback, useEffect, useRef, useState } from 'react';
import { api } from './api';
import { errorText } from './format';
import { useDraft } from './useDraft';
import { useTask } from './useTask';
import type { JobStatus, RunOptions } from './types';
export function useWorkspace() {
  const draft = useDraft();
  const [options, setOptions] = useState<RunOptions | null>(null), [error, setError] = useState('');
  const [busy, setBusy] = useState(false), [currentId, setCurrentId] = useState<string | null>(null);
  const [page, setPage] = useState('工作台');
  const [view, setView] = useState('导入与设置'), [source, setSource] = useState('本地文件');
  const request = useRef<{ fingerprint: string; id: string } | null>(null);
  const current = useTask(currentId, true);
  const bootstrap = useCallback(async () => {
    try {
      const data = await api.bootstrap(); setOptions(data.defaults); setError('');
      setCurrentId(data.active_job_ids[0] ?? localStorage.getItem('bms-current-job'));
    } catch (cause) { setError(errorText(cause)); }
  }, []);
  useEffect(() => { void bootstrap(); }, [bootstrap]);
  const track = (id: string) => { localStorage.setItem('bms-current-job', id); setCurrentId(id); setView('队列与进度'); current.retry(); };
  const start = async () => {
    if (!options || busy || !draft.files.length) return;
    setBusy(true); setError('');
    try {
      const ids: string[] = [];
      for (const file of draft.files) ids.push((await draft.upload(file)).id);
      const fingerprint = JSON.stringify([ids, options]);
      if (request.current?.fingerprint !== fingerprint) request.current = { fingerprint, id: crypto.randomUUID() };
      const result = await api.start(ids, options, request.current.id);
      track(result.id); draft.clear(); request.current = null;
      return result.id;
    } catch (cause) { setError(errorText(cause)); }
    finally { setBusy(false); }
  };
  const action = async (work: () => Promise<unknown>) => { try { await work(); current.retry(); setError(''); } catch (cause) { setError(errorText(cause)); } };
  const rerun = async (job: JobStatus) => { await draft.reuse(job.upload_ids); setOptions(job.options); setSource('本地文件'); setView('导入与设置'); setPage('工作台'); };
  return { draft, options, setOptions, error, busy, start, currentId, current, track, action, rerun, bootstrap, page, setPage, view, setView, source, setSource };
}
