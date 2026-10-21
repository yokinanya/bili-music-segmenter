'use client';

import type { BatchItem, Clip, JobState, JobStatus } from '@/lib/types';
import { STATE_LABELS, StateBadge } from './StateBadge';
import { ClipList } from './ClipList';

interface Props {
  status: JobStatus;
  activeIndex: number;
  clips: Clip[];
  jobId: string;
  onSelectItem: (index: number) => void;
}

function progressPercent(status: JobStatus): number {
  if (status.batch.length === 0) return 0;
  const done = status.batch.filter((item) => item.state === 'succeeded').length;
  return Math.round((done / status.batch.length) * 100);
}

function itemDetail(item: BatchItem): string {
  switch (item.state) {
    case 'succeeded':
      return `${item.clip_count} 个片段`;
    case 'failed':
      return item.returncode === null ? '失败' : `退出码 ${item.returncode}`;
    case 'cancelled':
      return '已停止';
    default:
      return '';
  }
}

export function BatchProgress({ status, activeIndex, clips, jobId, onSelectItem }: Props) {
  const percent = progressPercent(status);
  const finished = status.state !== 'running' && status.batch_complete;
  return (
    <section className="card" aria-labelledby="batch-title">
      <div className="card-head">
        <h2 id="batch-title">批处理进度</h2>
        <div className="card-actions">
          <StateBadge state={status.state as JobState} />
        </div>
      </div>
      <div className="progress" role="progressbar" aria-valuemin={0} aria-valuemax={100} aria-valuenow={percent}>
        <div className="progress-fill" style={{ width: `${percent}%` }} />
      </div>
      <p className="muted small">
        {finished ? '已结束' : '处理中'} · 完成 {status.batch.filter((item) => item.state === 'succeeded').length} /{' '}
        {status.batch.length} · {percent}%
        {status.started_at && ` · 开始于 ${status.started_at.replace('T', ' ')}`}
        {status.finished_at && ` · 结束于 ${status.finished_at.replace('T', ' ')}`}
      </p>
      <ul className="batch-list">
        {status.batch.map((item, index) => (
          <li key={`${item.media}-${index}`} className={index === activeIndex ? 'active' : undefined}>
            <button type="button" className="batch-row" onClick={() => onSelectItem(index)}>
              <span className="batch-index">{index + 1}</span>
              <span className="file-name">{item.media}</span>
              <span className="muted small">{itemDetail(item)}</span>
              <StateBadge state={item.state} />
            </button>
          </li>
        ))}
      </ul>
      <p className="muted small">点击某个文件可查看它的日志。</p>
      {clips.length > 0 && <ClipList jobId={jobId} clips={clips} />}
      {finished && status.state === 'failed' && (
        <p className="notice danger" role="alert">
          最后一个失败文件的退出码为 {status.returncode}。请查看日志中的错误详情。
        </p>
      )}
      {status.accounting_errors.length > 0 && (
        <p className="notice warn" role="alert">
          统计不完整：{status.accounting_errors.join('；')}
        </p>
      )}
    </section>
  );
}

export const STATE_TEXT = STATE_LABELS;
