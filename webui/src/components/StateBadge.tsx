import type { ItemState, JobState } from '@/lib/types';

export const STATE_LABELS: Record<JobState | ItemState, string> = {
  running: '处理中',
  pending: '等待中',
  succeeded: '已完成',
  failed: '失败',
  cancelled: '已停止',
};

const TONE: Record<JobState | ItemState, string> = {
  running: 'info',
  pending: 'muted',
  succeeded: 'ok',
  failed: 'danger',
  cancelled: 'warn',
};

export function StateBadge({ state }: { state: JobState | ItemState }) {
  return (
    <span className={`badge badge-${TONE[state]}`}>
      {state === 'running' && <span className="dot" aria-hidden="true" />}
      {STATE_LABELS[state] ?? state}
    </span>
  );
}
