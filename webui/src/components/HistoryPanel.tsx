'use client';

import type { HistoryEntry } from '@/lib/types';
import { STATE_LABELS } from './StateBadge';

interface Props {
  entries: HistoryEntry[];
  currentId: string | null;
  onOpen: (entry: HistoryEntry) => void;
  onRerun: (entry: HistoryEntry) => void;
}

export function HistoryPanel({ entries, currentId, onOpen, onRerun }: Props) {
  return (
    <section className="card" aria-labelledby="history-title">
      <div className="card-head">
        <h2 id="history-title">任务历史</h2>
        <span className="muted small">{entries.length} 条</span>
      </div>
      {entries.length === 0 ? (
        <p className="muted">还没有已完成的任务。服务重启后仍会保留这里的历史。</p>
      ) : (
        <ul className="history-list">
          {[...entries].reverse().map((entry) => (
            <li key={entry.id} className={entry.id === currentId ? 'active' : undefined}>
              <div className="history-main">
                <span className={`badge badge-${entry.state === 'succeeded' ? 'ok' : entry.state === 'failed' ? 'danger' : 'warn'}`}>
                  {STATE_LABELS[entry.state]}
                </span>
                <span className="file-name">{entry.medias.join('、') || '（无文件名）'}</span>
                <span className="muted small">
                  {entry.finished_at.replace('T', ' ')} · {entry.clip_count} 个片段
                </span>
              </div>
              <div className="history-actions">
                <button type="button" className="btn ghost small" onClick={() => onOpen(entry)}>
                  查看
                </button>
                <button type="button" className="btn ghost small" onClick={() => onRerun(entry)}>
                  重新处理
                </button>
              </div>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
