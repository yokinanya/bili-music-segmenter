'use client';
import { useCallback, useEffect, useState } from 'react';
import { api } from './api';
import { errorText } from './format';
import type { HistoryEntry, UsageSnapshot } from './types';
const POLL_MS = 3000;

export function useUsageData() {
  const [session, setSession] = useState<UsageSnapshot | null>(null);
  const [entries, setEntries] = useState<HistoryEntry[]>([]);
  const [usageError, setUsageError] = useState(''), [historyError, setHistoryError] = useState('');
  const [revision, setRevision] = useState(0);
  const refresh = useCallback(() => setRevision((value) => value + 1), []);
  useEffect(() => {
    let alive = true, timer: ReturnType<typeof setTimeout>;
    const load = async () => {
      const [usage, history] = await Promise.allSettled([api.usage(), api.history()]);
      if (!alive) return;
      if (usage.status === 'fulfilled') { setSession(usage.value); setUsageError(''); }
      else setUsageError(errorText(usage.reason));
      if (history.status === 'fulfilled') { setEntries(history.value.entries); setHistoryError(''); }
      else setHistoryError(errorText(history.reason));
      timer = setTimeout(load, POLL_MS);
    };
    void load();
    return () => { alive = false; clearTimeout(timer); };
  }, [revision]);
  return { session, entries, usageError, historyError, refresh };
}
