'use client';
import { useCallback, useEffect, useState } from 'react';
import { api } from '@/lib/api';
import { errorText } from '@/lib/format';
import { useTask } from '@/lib/useTask';
import { isActive, type HistoryEntry, type JobStatus } from '@/lib/types';
import { Button, ListButton, MaterialDialog, Tabs } from './Material';
import { JobView } from './JobView';
import { StateBadge } from './StateBadge';
export function HistoryPanel({ onRerun, onResume }: { onRerun: (job: JobStatus) => Promise<void>; onResume: (id: string) => void }) {
  const [entries, setEntries] = useState<HistoryEntry[]>([]), [error, setError] = useState('');
  const [selected, setSelected] = useState<string | null>(null), [deleting, setDeleting] = useState(false);
  const [tab, setTab] = useState('队列与进度');
  const task = useTask(selected);
  const refresh = useCallback(async () => { try { setEntries((await api.history()).entries); setError(''); } catch (cause) { setError(errorText(cause)); } }, []);
  useEffect(() => { void refresh(); }, [refresh, task.job?.state]);
  const act = async (action: () => Promise<unknown>) => { try { await action(); setError(''); await refresh(); } catch (cause) { setError(errorText(cause)); } };
  const entry = entries.find((value) => value.id === selected);
  return <div className={`history-layout ${tab === '日志与结果' ? 'show-output' : 'show-queue'}`}>
    <div className="task-tabs"><Tabs value={tab} options={['队列与进度', '日志与结果']} onChange={setTab} /></div>
    <section className="panel history-list"><div className="pane-heading"><h2>任务列表</h2><Button variant="text" onClick={() => void refresh()}>刷新</Button></div><div className="history-scroll">
    {error && <div className="error" role="alert">{error}<Button onClick={() => void refresh()}>重试</Button></div>}
    {!entries.length && <p className="empty">尚无历史任务</p>}
    <ol className="list list-segmented">{entries.map((item) => <li key={item.id}><ListButton selected={selected === item.id} onClick={() => setSelected(item.id)}><span className="list-item-content"><strong>{item.medias?.join('、') || '旧任务'}</strong><span className="list-item-supporting-text">{new Date(item.started_at).toLocaleString()} · {item.clip_count} 个片段</span></span><StateBadge state={item.state} /></ListButton></li>)}</ol>
  </div></section>
  {entry?.legacy ? <section className="panel history-empty empty">{entry.availability}</section> : <>
    {task.job && <JobView key={task.job.id} job={task.job} error={task.error} onRetry={task.retry} actions={<>
      {!isActive(task.job.state) && task.job.state !== 'cleanup_pending' && <Button onClick={() => void act(() => onRerun(task.job!))}>重新处理</Button>}
      {['failed', 'cancelled', 'interrupted'].includes(task.job.state) && <Button variant="filled" onClick={() => void act(async () => { await api.retry(task.job!.id); onResume(task.job!.id); task.retry(); })}>续跑未完成步骤</Button>}
      {isActive(task.job.state) ? <Button onClick={() => void act(() => api.stop(task.job!.id))}>停止任务</Button> : <Button variant="text" onClick={() => setDeleting(true)}>{task.job.state === 'cleanup_pending' ? '再次清理' : '删除任务'}</Button>}
    </>} />}
    {!task.job && <div className="panel history-empty empty">{task.error ? <div className="error" role="alert">{task.error}<Button onClick={task.retry}>重新读取详情</Button></div> : selected ? '正在读取…' : '选择历史任务'}</div>}
  </>}
  <MaterialDialog open={deleting} title="删除任务与文件？" onClose={() => setDeleting(false)}><p>删除该任务的结果，并清理没有其他任务引用的源文件和 S3 缓存。此操作无法撤销。</p><div className="dialog-actions"><Button onClick={() => setDeleting(false)}>取消</Button><Button variant="filled" onClick={() => void act(async () => { await api.delete(selected!); setDeleting(false); setSelected(null); })}>确认删除</Button></div></MaterialDialog>
  </div>;
}
