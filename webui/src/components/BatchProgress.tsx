import type { BatchItem, JobState, JobStatus } from '@/lib/types';
import { isActive } from '@/lib/types';
import { elapsed } from '@/lib/format';
import { Button, ListButton, Progress } from './Material';
import { StateBadge } from './StateBadge';
import { StepGroup, UploadSteps } from './ProgressSteps';

export function BatchProgress({ job, selected, onSelect, onFollow, following }: { job: JobStatus; selected: number; onSelect: (value: number) => void; onFollow: () => void; following: boolean }) {
  const ended = job.batch.filter((item) => !isActive(item.state)).length;
  const single = job.batch.length === 1;
  return <section className={`queue-panel ${single ? 'single-video-summary' : ''}`}><div className="section-head"><h2>{single ? '视频处理' : '处理队列'}</h2><StateBadge state={job.state} /></div>
    <div className="batch-summary"><strong>{single ? job.batch[0].media : <>{ended}<span className="muted"> / {job.batch.length}</span></>}</strong><span className="muted">{single ? '' : '视频已结束 · '}{elapsed(job.started_at, job.finished_at)}</span></div>
    {!single && job.batch.length > 0 && <Progress label="整批视频已结束数量" value={ended / job.batch.length} />}
    {!single && <div className="count-row">{(['succeeded', 'failed', 'cancelled', 'interrupted'] as const).map((state) => <span key={state}>{{ succeeded: '成功', failed: '失败', cancelled: '已停止', interrupted: '已中断' }[state]} {job.batch.filter((item) => item.state === state).length}</span>)}</div>}
    {!single && <ol className="list list-segmented queue-list">{job.batch.map((item, index) => <li key={item.id}>
      <ListButton selected={index === selected} onClick={() => onSelect(index)}><span className="queue-number">{String(index + 1).padStart(2, '0')}</span><span className="list-item-content"><strong>{item.media}</strong><span className="list-item-supporting-text">{elapsed(item.started_at, item.finished_at)}</span></span><StateBadge state={item.state} /></ListButton>
    </li>)}</ol>}{!single && !following && isActive(job.state) && <Button variant="text" onClick={onFollow}>跟随当前视频</Button>}
  </section>;
}
function emptyMessage(item: BatchItem, jobState?: JobState) {
  if (jobState && !isActive(jobState) && isActive(item.state)) return '任务已结束，此视频未处理';
  if (isActive(item.state)) return '等待视频开始处理';
  if (item.state === 'succeeded') return '视频处理已完成，未记录步骤';
  if (item.state === 'cancelled') return '视频已停止，没有可显示的步骤';
  if (item.state === 'interrupted') return '视频处理中断，没有可显示的步骤';
  return '视频处理已结束，没有可显示的步骤';
}
export function VideoProgress({ item, jobState }: { item: BatchItem; jobState?: JobState }) {
  const roots = item.steps.filter((step) => !step.parent_id || !item.steps.some((parent) => parent.id === step.parent_id));
  return <section className="steps-panel"><div className="section-head"><h2>步骤进度</h2></div>
    <p className="selected-name">{item.media}</p>{item.error && <div className="error" role="alert">{item.error}</div>}
    {!roots.length && <div className="empty small-empty">{emptyMessage(item, jobState)}</div>}
    <StepGroup steps={roots} allSteps={item.steps} /><UploadSteps item={item} />
  </section>;
}
