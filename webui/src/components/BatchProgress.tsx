import type { BatchItem, JobStatus, ProgressStep } from '@/lib/types';
import { isActive } from '@/lib/types';
import { bytes, elapsed } from '@/lib/format';
import { Button, ListButton, Progress } from './Material';
import { StateBadge } from './StateBadge';
import { Disclosure } from './Disclosure';
export function BatchProgress({ job, selected, onSelect, onFollow, following }: { job: JobStatus; selected: number; onSelect: (value: number) => void; onFollow: () => void; following: boolean }) {
  const done = job.batch.filter((item) => !isActive(item.state)).length;
  return <section className="queue-panel"><div className="section-head"><h2>处理队列</h2><StateBadge state={job.state} /></div>
    <div className="batch-summary"><strong>{done}<span className="muted"> / {job.batch.length}</span></strong><span className="muted">视频已处理 · {elapsed(job.started_at, job.finished_at)}</span></div>
    <Progress label="整批视频完成数量" value={done / job.batch.length} />
    <div className="count-row">{(['succeeded', 'failed', 'cancelled'] as const).map((state) => <span key={state}>{state === 'succeeded' ? '成功' : state === 'failed' ? '失败' : '停止'} {job.batch.filter((item) => item.state === state).length}</span>)}</div>
    <ol className="list list-segmented queue-list">{job.batch.map((item, index) => <li key={item.id}>
      <ListButton selected={index === selected} onClick={() => onSelect(index)}><span className="queue-number">{String(index + 1).padStart(2, '0')}</span><span className="list-item-content"><strong>{item.media}</strong><span className="list-item-supporting-text">{elapsed(item.started_at, item.finished_at)}</span></span><StateBadge state={item.state} /></ListButton>
    </li>)}</ol>{!following && <Button variant="text" onClick={onFollow}>跟随当前视频</Button>}
  </section>;
}
export function VideoProgress({ item }: { item: BatchItem }) {
  const steps = item.steps.filter((step) => !step.parent_id);
  const orphans = item.steps.filter((step) => step.parent_id && !item.steps.some((parent) => parent.id === step.parent_id));
  return <section className="steps-panel"><div className="section-head"><h2>步骤进度</h2></div>
    <p className="selected-name">{item.media}</p>{item.error && <div className="error" role="alert">{item.error}</div>}
    {!steps.length && <div className="empty small-empty">等待视频开始处理</div>}
    {[...steps, ...orphans].map((step) => <Step key={step.id} step={step} steps={item.steps} />)}
    {item.upload?.uploads?.map((upload) => <div className="upload-step" key={upload.key}><span>S3 上传 · {upload.state}</span><Progress value={upload.transferred_bytes / upload.total_bytes} label="S3 上传字节进度" /><span className="muted">{bytes(upload.transferred_bytes)} / {bytes(upload.total_bytes)}</span></div>)}
  </section>;
}
function Step({ step, steps }: { step: ProgressStep; steps: ProgressStep[] }) {
  const children = steps.filter((item) => item.parent_id === step.id);
  const measured = step.total !== null && step.total > 0;
  const counter = measured ? `${Number(step.completed.toFixed(1))} / ${Number(step.total!.toFixed(1))} ${step.unit ?? ''}` : '';
  return <div className="step"><div className="step-head"><strong>{step.label}</strong><StateBadge state={step.state} /></div>
    {measured && <><Progress value={step.completed / step.total!} label={`${step.label} ${counter}`} /><div className="step-meta">{counter}{step.elapsed_seconds !== undefined && <span>{step.elapsed_seconds.toFixed(1)}秒</span>}</div></>}
    {step.message && <span className="muted">{step.message}</span>}{step.error && <p className="error-text">{step.error}</p>}
    {children.length > 0 && <Disclosure title={`子步骤 · ${children.length}`} defaultOpen={['running', 'waiting', 'failed'].includes(step.state)}>{children.map((child) => <Step key={child.id} step={child} steps={steps} />)}</Disclosure>}
  </div>;
}
