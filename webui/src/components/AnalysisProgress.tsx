'use client';
import type { JobStatus } from '@/lib/types';
import { summarizeProgress } from '@/lib/progressSummary';
import { Progress } from './Material';

export function AnalysisProgress({ job }: { job: JobStatus }) {
  const item = job.batch.find(value => value.state === 'running');
  const summary = item ? summarizeProgress({ job, item }) : null;
  const measurement = summary?.measurement;
  return <div className="analysis-progress" role="status">
    <span>{summary?.path || '等待任务执行'}</span>
    <Progress label="AI切片当前步骤进度" value={measurement ? measurement.completed / measurement.total : undefined} />
    {measurement && <small>{measurement.completed} / {measurement.total} {measurement.unit} · 当前步骤</small>}
  </div>;
}
