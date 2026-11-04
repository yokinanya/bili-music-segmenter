'use client';
import { useState } from 'react';
import type { JobStatus } from '@/lib/types';
import { BatchProgress, VideoProgress } from './BatchProgress';
import { ClipList } from './ClipList';
import { LogViewer } from './LogViewer';
import { Button, Tabs } from './Material';
export function JobView({ job, actions, error, onRetry }: { job: JobStatus; actions?: React.ReactNode; error?: string; onRetry?: () => void }) {
  const [manual, setManual] = useState<number | null>(null);
  const [tab, setTab] = useState('结果');
  const index = manual ?? job.current_index ?? Math.max(0, job.batch.findIndex((item) => item.state !== 'succeeded'));
  const item = job.batch[index] ?? job.batch[0];
  return <><section className="panel task-main"><div className="task-scroll">
    {error && <div className="error" role="alert">{error}<Button onClick={onRetry}>重新读取</Button></div>}
    <BatchProgress job={job} selected={index} onSelect={setManual} following={manual === null} onFollow={() => setManual(null)} />
    {job.error && <div className="error">{job.error}</div>}{job.cleanup_error && <div className="error">清理失败：{job.cleanup_error}</div>}
    <VideoProgress item={item} /></div><div className="pane-footer task-actions">{actions}</div>
  </section><section className="panel output-panel"><Tabs value={tab} options={['结果', '日志']} onChange={setTab} />
    <div className={`output-body ${tab === '日志' ? 'log-body' : ''}`}>
      {tab === '结果' ? <ClipList job={job} mediaId={item.id} /> : <LogViewer key={`${job.id}:${index}:${job.attempt}`} jobId={job.id} index={index} />}
    </div>
  </section></>;
}
