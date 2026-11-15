'use client';
import { useCallback, useEffect, useRef, useState } from 'react';
import { api } from './api';
import { errorText } from './format';
import { useDraft } from './useDraft';
import { useTask } from './useTask';
import { useNavigation } from './useNavigation';
import type { Page } from './navigation';
import type { JobStatus, RunOptions } from './types';
export function useWorkspace() {
  const draft = useDraft();
  const [options, setOptions] = useState<RunOptions | null>(null), [error, setError] = useState('');
  const [busy, setBusy] = useState(false), [currentId, setCurrentId] = useState<string | null>(null);
  const { navigation, navigate } = useNavigation();
  const { page, view, source } = navigation;
  const [downloadUrl, setDownloadUrl] = useState('');
  const setPage = (page: Page) => navigate({ page });
  const setView = (view: string) => navigate({ view });
  const setSource = (source: string) => navigate({ source });
  const request = useRef<{ fingerprint: string; id: string } | null>(null);
  const trackedId = currentId;
  const current = useTask(trackedId, true);
  const bootstrap = useCallback(async () => {
    try {
      const data = await api.bootstrap(); setOptions(data.defaults); setError('');
      setCurrentId(data.active_job_ids[0] ?? null);
    } catch (cause) { setError(errorText(cause)); }
  }, []);
  useEffect(() => { void bootstrap(); }, [bootstrap]);
  const track = (id: string) => { setCurrentId(id); navigate({ page: '链接下载', view: '队列与进度' }); current.retry(); };
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
  return { draft, options, setOptions, error, busy, start, currentId: trackedId, current, track, action, downloadUrl, setDownloadUrl, bootstrap, page, setPage, view, setView, source, setSource, navigation, navigate };
  }
