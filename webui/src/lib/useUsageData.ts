'use client';
import { useCallback, useEffect, useState } from 'react';
import { api } from './api';
import { errorText } from './format';
import type { UsageSnapshot } from './types';

const POLL_MS = 5000;

/** Usage totals are cumulative and persisted in SQLite, so they never depend on task records. */
export function useUsageData() {
  const [session, setSession] = useState<UsageSnapshot | null>(null);
  const [usageError, setUsageError] = useState('');
  const [revision, setRevision] = useState(0);
  const refresh = useCallback(() => setRevision((value) => value + 1), []);
  useEffect(() => {
    let alive = true, timer: ReturnType<typeof setTimeout>;
    const load = async () => {
      try { const usage = await api.usage(); if (!alive) return; setSession(usage); setUsageError(''); }
      catch (cause) { if (!alive) return; setUsageError(errorText(cause)); }
      if (alive) timer = setTimeout(load, POLL_MS);
    };
    void load();
    return () => { alive = false; clearTimeout(timer); };
  }, [revision]);
  return { session, usageError, refresh };
}
