'use client';
import { useCallback, useEffect, useState } from 'react';
import { api } from '@/lib/api';
import { errorText } from '@/lib/format';
import { useTask } from '@/lib/useTask';
import { useNavigation } from '@/lib/useNavigation';
import { isActive, type HistoryEntry, type JobStatus } from '@/lib/types';
import { Button, ListButton, MaterialDialog, Select, Tabs, TextField } from './Material';
import { JobView } from './JobView';
import { StateBadge } from './StateBadge';
const HISTORY_STATES = [
  { value: 'all', label: '全部状态' }, { value: 'queued', label: '排队中' },
  { value: 'running', label: '处理中' }, { value: 'succeeded', label: '已成功' },
  { value: 'failed', label: '失败' }, { value: 'cancelled', label: '已停止' },
  { value: 'interrupted', label: '已中断' }, { value: 'cleanup_pending', label: '待清理' },
];
interface HistoryPanelProps {
  onRerun: (job: JobStatus) => Promise<void>; onResume: (id: string) => void;
  onRedownload?: (job: JobStatus) => void;
  selectedId?: string | null; onSelect?: (id: string | null) => void;
  view?: string; onView?: (value: string) => void;
}
export function HistoryPanel({ onRerun, onResume, onRedownload, selectedId, onSelect, view, onView }: HistoryPanelProps) {
  const [entries, setEntries] = useState<HistoryEntry[]>([]), [error, setError] = useState('');
  const [localSelected, setLocalSelected] = useState<string | null>(null), [deleting, setDeleting] = useState(false);
  const [localTab, setLocalTab] = useState('队列与进度');
  const { navigation, navigate } = useNavigation();
  const query = navigation.query, state = navigation.status;
  const setQuery = (query: string) => navigate({ query });
  const setState = (status: string) => navigate({ status });
  const selected = selectedId === undefined ? localSelected : selectedId;
  const tab = view ?? localTab;
  const setSelected = (id: string | null) => { setLocalSelected(id); onSelect?.(id); };
  const setTab = (value: string) => { setLocalTab(value); onView?.(value); };
  const task = useTask(selected);
  const refresh = useCallback(async () => { try { setEntries((await api.history()).entries); setError(''); } catch (cause) { setError(errorText(cause)); } }, []);
  useEffect(() => { void refresh(); }, [refresh, task.job?.state]);
  const act = async (action: () => Promise<unknown>) => { try { await action(); setError(''); await refresh(); } catch (cause) { setError(errorText(cause)); } };
  const entry = entries.find((value) => value.id === selected);
  const search = query.trim().toLocaleLowerCase();
  const filtered = entries.filter((item) => (state === 'all' || item.state === state) && `${item.id} ${item.medias.join(' ')}`.toLocaleLowerCase().includes(search));
  return <div className={`history-layout ${tab === '日志与结果' ? 'show-output' : 'show-queue'}`}>
    <div className="task-tabs"><Tabs value={tab} options={['队列与进度', '日志与结果']} onChange={setTab} /></div>
    <section className="panel history-list"><div className="pane-heading"><h2>任务列表</h2><Button variant="text" onClick={() => void refresh()}>刷新</Button></div><div className="history-filters"><TextField label="搜索文件名或任务 ID" value={query} onChange={setQuery} /><Select label="任务状态" value={state} onChange={setState} options={HISTORY_STATES} /></div><div className="history-scroll">
    {error && <div className="error" role="alert">{error}<Button onClick={() => void refresh()}>重试</Button></div>}
    {!entries.length && <p className="empty">尚无历史任务</p>}
    {entries.length > 0 && !filtered.length && <p className="empty">没有符合搜索和状态条件的任务</p>}
    <ol className="list list-segmented">{filtered.map((item) => <li key={item.id}><ListButton selected={selected === item.id} onClick={() => setSelected(item.id)}><span className="list-item-content"><strong>{item.medias?.join('、') || '旧任务'}</strong><span className="list-item-supporting-text">{new Date(item.started_at).toLocaleString()} · {item.clip_count} 个片段</span></span><StateBadge state={item.state} /></ListButton></li>)}</ol>
  </div></section>
  {entry?.legacy ? <section className="panel history-empty empty">{entry.availability}</section> : <>
    {task.job && <JobView key={task.job.id} job={task.job} error={task.error} onRetry={task.retry} actions={<>
      {!isActive(task.job.state) && task.job.state !== 'cleanup_pending' && <>
        <Button disabled={task.job.batch.some((item) => item.can_reuse === false)} onClick={() => void act(() => onRerun(task.job!))}>{task.job.batch.some((item) => item.source_type === 'download') ? '复用视频重新分析' : '重新处理'}</Button>
        {task.job.batch.some((item) => item.can_reuse === false) && <span className="helper">源视频不可用，无法复用</span>}
        {onRedownload && task.job.batch.some((item) => item.source_url) && <Button onClick={() => onRedownload(task.job!)}>重新下载原链接</Button>}
      </>}
      {(task.job.can_complete_parts || ['failed', 'cancelled', 'interrupted'].includes(task.job.state)) && <Button variant="filled" onClick={() => void act(async () => { await api.retry(task.job!.id); onResume(task.job!.id); task.retry(); })}>{task.job.can_complete_parts ? '补齐分 P' : '续跑未完成步骤'}</Button>}
      {isActive(task.job.state) ? <Button onClick={() => void act(() => api.stop(task.job!.id))}>停止任务</Button> : <Button variant="text" onClick={() => setDeleting(true)}>{task.job.state === 'cleanup_pending' ? '再次清理' : '删除任务'}</Button>}
    </>} />}
    {!task.job && <div className="panel history-empty empty">{task.error ? <div className="error" role="alert">{task.error}<Button onClick={task.retry}>重新读取详情</Button></div> : selected ? '正在读取…' : '选择历史任务'}</div>}
  </>}
  <MaterialDialog open={deleting} title="删除任务与文件？" onClose={() => setDeleting(false)}><p>删除该任务的结果，并清理没有其他任务引用的源文件和音频缓存。此操作无法撤销。</p><div className="dialog-actions"><Button onClick={() => setDeleting(false)}>取消</Button><Button variant="filled" onClick={() => void act(async () => { await api.delete(selected!); setDeleting(false); setSelected(null); })}>确认删除</Button></div></MaterialDialog>
  </div>;
}
