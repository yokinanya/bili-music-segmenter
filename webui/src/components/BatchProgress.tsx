import type { BatchItem, JobStatus } from '@/lib/types';
import { isActive } from '@/lib/types';
import { bytes, elapsed, progressCounter } from '@/lib/format';
import { summarizeBatch, summarizeProgress } from '@/lib/progressSummary';
import { Button, ListButton, Progress } from './Material';
import { StateBadge } from './StateBadge';
import { ProgressDetails, ProgressErrors } from './ProgressSteps';

interface BatchProgressProps {
  job: JobStatus;
  selected: number;
  onSelect: (value: number) => void;
  onFollow: () => void;
  following: boolean;
}

export function BatchProgress({ job, selected, onSelect, onFollow, following }: BatchProgressProps) {
  const { ended, issues } = summarizeBatch(job.batch);
  const single = job.batch.length === 1;
  return <section className="queue-panel">
    <div className="section-head"><h2>{single ? '视频处理' : '处理队列'}</h2><StateBadge state={job.state} /></div>
    {single && <p className="queue-media">{job.batch[0].media}</p>}
    <div className="batch-summary">
      {!single && <span>已结束 <strong>{ended} / {job.batch.length}</strong></span>}
      <span>总耗时 {elapsed(job.started_at, job.finished_at)}</span>
      {!single && issues.map(({ label, count }) => <span className="batch-issue" key={label}>{label} {count}</span>)}
    </div>
    {!single && <ol className="list list-segmented queue-list">{job.batch.map((item, index) =>
      <li key={item.id}><ListButton selected={index === selected} onClick={() => onSelect(index)}>
        <span className="list-item-content"><strong>{item.media}</strong></span>
        <StateBadge state={item.state} />
      </ListButton></li>)}</ol>}
    {!single && !following && isActive(job.state) && <Button variant="text" onClick={onFollow}>跟随当前视频</Button>}
  </section>;
}

export function VideoProgress({ item, job }: { item: BatchItem; job: JobStatus }) {
  const summary = summarizeProgress({ item, job });
  return <section className="steps-panel">
    <div className="section-head"><h2>当前进度</h2><StateBadge state={summary.current?.step.state ?? summary.state} /></div>
    <CurrentProgress summary={summary} />
    {summary.unprocessed && <p className="muted progress-note">任务已结束，此视频未处理</p>}
    {!summary.details.length && <p className="muted progress-note">尚无步骤记录</p>}
    <ProgressErrors issues={summary.issues} />
    <ProgressDetails steps={summary.details} />
  </section>;
}

function CurrentProgress({ summary }: { summary: ReturnType<typeof summarizeProgress> }) {
  const { current, measurement, path, counterPrefix } = summary;
  const counter = currentCounter(summary);
  return <div className="current-progress">
    <p className="current-work" aria-live="polite">{path}</p>
    <CurrentMeasurement running={summary.running} measurement={measurement}
      label={counter ? `${path} ${counter}` : path || '视频处理进度'} />
    {counter && <p className="progress-counter">{counter}</p>}
    {summary.parallelCount > 0 && <p className="muted">同时还有 {summary.parallelCount} 项在处理</p>}
    {current?.step.message && <p className="muted progress-message">{current.step.message}</p>}
  </div>;
}

function currentCounter({ measurement, current, counterPrefix }: ReturnType<typeof summarizeProgress>) {
  const counterStep = measurement ?? current?.step;
  if (!counterStep) return '';
  const count = progressCounter(counterStep);
  return count ? `${counterPrefix}${count}` : '';
}

function CurrentMeasurement({ running, measurement, label }: {
  running: boolean;
  measurement: ReturnType<typeof summarizeProgress>['measurement'];
  label: string;
}) {
  if (!running) return null;
  return <Progress value={measurement ? measurement.completed / measurement.total : undefined}
    label={label} />;
}
