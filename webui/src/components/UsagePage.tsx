'use client';
import { useNavigation } from '@/lib/useNavigation';
import { useTask } from '@/lib/useTask';
import { useUsageData } from '@/lib/useUsageData';
import { Button, Select } from './Material';
import { UsagePanel } from './UsagePanel';
import { Disclosure } from './Disclosure';
import { StateBadge } from './StateBadge';
import { isActive, type JobStatus } from '@/lib/types';
import { attemptUsage } from './attemptUsage';
function executionRows(job: JobStatus) {
  const previous = job.attempts.filter((attempt) => !isActive(job.state) || attempt.number !== job.attempt).map((attempt) => ({ ...attempt, current: false }));
  return isActive(job.state) ? [...previous, { number: job.attempt, state: job.state, usage: attemptUsage(job), current: true }] : previous;
}
export function UsagePage({ currentId }: { currentId: string | null }) {
  const { session, entries, usageError, historyError, refresh } = useUsageData();
  const { navigation, navigate } = useNavigation();
  const selected = navigation.usage === 'none' ? null : navigation.usage || currentId;
  const setSelected = (id: string | null) => navigate({ usage: id ?? 'none' });
  const task = useTask(selected);
  return <div className="usage-page">
    {usageError && <div className="error" role="alert">用量读取失败：{usageError}<Button onClick={refresh}>重试</Button></div>}
    {historyError && <div className="error" role="alert">任务列表读取失败：{historyError}<Button onClick={refresh}>重试</Button></div>}
    <div className="usage-toolbar"><Select label="查看任务" value={selected ?? ''} onChange={(value) => setSelected(value || null)}
      options={[{ value: '', label: '未选择任务' }, ...entries.filter((entry) => !entry.legacy).map((entry) => ({ value: entry.id, label: `${new Date(entry.started_at).toLocaleString()} · ${entry.medias.join('、')}` }))]} />
      <Button variant="outlined" onClick={refresh}>刷新用量</Button></div>
    {task.error && <div className="error">{task.error}<Button onClick={task.retry}>重新读取任务</Button></div>}
    <UsagePanel session={session} job={task.job?.usage ?? null} />
    {task.job && <section className="panel"><h2>执行记录</h2><div className="table-scroll"><table><thead><tr><th>执行次数</th><th>状态</th><th>模型调用</th><th>估算费用</th></tr></thead><tbody>{executionRows(task.job).map((attempt) => <tr key={attempt.number}><td>第 {attempt.number} 次{attempt.current ? ' · 当前' : ''}</td><td><StateBadge state={attempt.state} /></td><td>{attempt.usage.calls}</td><td>{attempt.usage.complete ? '' : '已知部分 ' }¥{attempt.usage.estimated_cny.toFixed(6)}</td></tr>)}</tbody></table></div>
      <Disclosure title={`模型请求 · ${task.job.usage_events.length} 次`}><ol className="call-list">{task.job.usage_events.map((event, index) => <li key={index}>第 {event.attempt} 次执行 · {event.model} · {new Date(event.at).toLocaleTimeString()}</li>)}</ol></Disclosure>
    </section>}
  </div>;
}
