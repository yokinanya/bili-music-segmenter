import type { StepState } from '@/lib/types';
export const stateLabel: Record<StepState, string> = {
  queued: '等待执行', running: '执行中', succeeded: '已完成', failed: '失败', cancelled: '已停止',
  interrupted: '执行中断', cleanup_pending: '清理未完成', waiting: '等待资源', reused: '缓存复用', skipped: '已跳过', retrying: '重试中',
};
export function StateBadge({ state }: { state: StepState }) {
  return <span className={`badge state-${state}`}><span className="status-dot" />{stateLabel[state]}</span>;
}
