'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import { ApiError, api } from './api';
import type { JobStatus, LogChunk } from './types';

const ACTIVE_INTERVAL_MS = 1000;
const SETTLED_INTERVAL_MS = 5000;
const FIRST_BACKOFF_MS = 1000;
const MAX_BACKOFF_MS = 15000;

export type Connection = 'idle' | 'online' | 'retrying' | 'offline';

export interface JobFeed {
  status: JobStatus | null;
  connection: Connection;
  lastError: string | null;
  /** Append-only log text per batch item index. */
  logs: Record<number, string>;
  retry: () => void;
}

/**
 * Polls one job until it settles. Transient failures back off instead of tearing the UI down,
 * so a sleeping laptop recovers on its own; only a missing job (404) stops polling.
 */
export function useJob(jobId: string | null): JobFeed {
  const [status, setStatus] = useState<JobStatus | null>(null);
  const [connection, setConnection] = useState<Connection>('idle');
  const [lastError, setLastError] = useState<string | null>(null);
  const [logs, setLogs] = useState<Record<number, string>>({});
  const [attemptSeed, setAttemptSeed] = useState(0);
  const retry = useCallback(() => setAttemptSeed((value) => value + 1), []);

  useEffect(() => {
    if (!jobId) {
      setStatus(null);
      setConnection('idle');
      setLogs({});
      return;
    }
    let disposed = false;
    let timer: number | undefined;
    let attempt = 0;
    const offsets: Record<number, number> = {};
    setLogs({});
    setStatus(null);

    const sleep = (delay: number) => {
      timer = window.setTimeout(tick, delay);
    };

    const pullLog = async (id: string, index: number, state: string) => {
      if (state === 'pending' || state === 'cancelled') return;
      try {
        const chunk: LogChunk = await api.log(id, index, offsets[index] ?? 0);
        if (disposed) return;
        offsets[index] = chunk.offset;
        if (chunk.text) setLogs((previous) => ({ ...previous, [index]: (previous[index] ?? '') + chunk.text }));
      } catch {
        // Logs are secondary; their failure must not block the status view.
      }
    };

    const tick = async () => {
      if (disposed) return;
      try {
        const next = await api.job(jobId);
        if (disposed) return;
        setStatus(next);
        setConnection('online');
        setLastError(null);
        attempt = 0;
        await Promise.all(next.batch.map((item, index) => pullLog(jobId, index, item.state)));
        if (disposed) return;
        const settled = next.state !== 'running' && next.batch_complete;
        sleep(settled ? SETTLED_INTERVAL_MS : ACTIVE_INTERVAL_MS);
      } catch (cause) {
        if (disposed) return;
        const error = cause instanceof ApiError ? cause : new ApiError('未知错误', 0);
        setLastError(error.message);
        if (error.status === 404) {
          // The job no longer exists (service restarted); stop polling instead of looping forever.
          setConnection('offline');
          return;
        }
        attempt += 1;
        setConnection('retrying');
        sleep(Math.min(FIRST_BACKOFF_MS * 2 ** (attempt - 1), MAX_BACKOFF_MS));
      }
    };

    void tick();
    return () => {
      disposed = true;
      window.clearTimeout(timer);
    };
  }, [jobId, attemptSeed]);

  return { status, connection, lastError, logs, retry };
}
