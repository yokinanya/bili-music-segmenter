'use client';
import { useEffect, useState } from 'react';
import type { ClipEditProgress as EditProgress } from '@/lib/types';
import { mediaTime } from '@/lib/format';
import { Progress } from './Material';

const CLOCK_INTERVAL_MS = 1000;

export function ClipEditProgress({ progress }: { readonly progress: EditProgress }) {
  const [startedAt] = useState(Date.now);
  const [elapsed, setElapsed] = useState(0);
  useEffect(() => {
    const timer = setInterval(() => setElapsed((Date.now() - startedAt) / CLOCK_INTERVAL_MS), CLOCK_INTERVAL_MS);
    return () => clearInterval(timer);
  }, [startedAt]);
  const ratio = progress.total_seconds === null ? undefined : progress.completed_seconds / progress.total_seconds;
  const percent = ratio === undefined ? '' : ` ${Math.round(ratio * 100)}%`;
  const label = progress.stage === 'preparing' ? '正在准备' : progress.stage === 'saving' ? '正在保存结果' : `正在导出${percent}`;
  return <div className="clip-edit-progress">
    <p role="status" aria-live="polite">{label}</p>
    <Progress value={ratio} label={label} />
    <p className="helper">
      {progress.total_seconds !== null && <>已处理 {mediaTime(progress.completed_seconds)} / {mediaTime(progress.total_seconds)} · </>}
      已用时 {mediaTime(Math.max(elapsed, progress.elapsed_seconds))}
    </p>
  </div>;
}
