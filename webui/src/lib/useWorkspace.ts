'use client';
import { useCallback, useEffect, useRef, useState } from 'react';
import { api } from './api';
import { errorText } from './format';
import { useDraft } from './useDraft';
import { useTask } from './useTask';
import { useNavigation } from './useNavigation';
import type { JobStatus, RunOptions } from './types';
export function useWorkspace() {
  const draft = useDraft();
  const [options, setOptions] = useState<RunOptions | null>(null), [error, setError] = useState('');
  const [busy, setBusy] = useState(false), [currentId, setCurrentId] = useState<string | null>(null);
  const { navigation, navigate } = useNavigation();
  const { page, view, source } = navigation;
  const [downloadUrl, setDownloadUrl] = useState('');
  const setPage = (page: string) => navigate({ page });
  const setView = (view: string) => navigate({ view });
  const setSource = (source: string) => navigate({ source });
  const request = useRef<{ fingerprint: string; id: string } | null>(null);
  const trackedId = navigation.job || currentId;
  const current = useTask(trackedId, true);
  const bootstrap = useCallback(async () => {
    try {
      const data = await api.bootstrap(); setOptions(data.defaults); setError('');
      setCurrentId(data.active_job_ids[0] ?? localStorage.getItem('bms-current-job'));
    } catch (cause) { setError(errorText(cause)); }
  }, []);
  useEffect(() => { void bootstrap(); }, [bootstrap]);
  const track = (id: string) => { localStorage.setItem('bms-current-job', id); setCurrentId(id); navigate({ job: id, page: '工作台', view: '队列与进度' }); current.retry(); };
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
  const rerun = async (job: JobStatus) => { await draft.reuse(job.upload_ids); setOptions(job.options); navigate({ source: '本地文件', view: '导入与设置', page: '工作台' }); };
  const redownload = (job: JobStatus) => {
    const url = job.batch.find((item) => item.source_url)?.source_url;
    if (!url) throw new Error('任务没有可重新下载的源链接');
    setDownloadUrl(url); setOptions(job.options);
    navigate({ source: '视频链接', view: '导入与设置', page: '工作台' });
  };
  return { draft, options, setOptions, error, busy, start, currentId: trackedId, current, track, action, rerun, redownload, downloadUrl, setDownloadUrl, bootstrap, page, setPage, view, setView,   source, setSource, navigation, navigate };
  }
