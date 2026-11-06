import type { BatchItem, ProgressStep } from '@/lib/types';
import { bytes } from '@/lib/format';
import { Progress } from './Material';
import { StateBadge } from './StateBadge';
import { Disclosure } from './Disclosure';

const completed = (state: string) => ['succeeded', 'reused', 'skipped'].includes(state);
function completedBranch(step: ProgressStep, steps: ProgressStep[]): boolean {
  return completed(step.state) && steps.filter((child) => child.parent_id === step.id).every((child) => completedBranch(child, steps));
}

export function StepGroup({ steps, allSteps }: { steps: ProgressStep[]; allSteps: ProgressStep[] }) {
  const ended = steps.filter((step) => completedBranch(step, allSteps));
  const visible = steps.filter((step) => !ended.includes(step));
  return <>{visible.map((step) => <Step key={step.id} step={step} steps={allSteps} />)}
    {ended.length > 0 && <Disclosure title={`已完成步骤 · ${ended.length}`}>
      {ended.map((step) => <Step key={step.id} step={step} steps={allSteps} />)}
    </Disclosure>}
  </>;
}
function Step({ step, steps }: { step: ProgressStep; steps: ProgressStep[] }) {
  const children = steps.filter((item) => item.parent_id === step.id);
  const measured = step.total !== null && step.total > 0;
  const counter = measured ? `${Number(step.completed.toFixed(1))} / ${Number(step.total!.toFixed(1))} ${step.unit ?? ''}` : '';
  return <div className="step"><div className="step-head"><strong>{step.label}</strong><StateBadge state={step.state} /></div>
    {measured && <><Progress value={step.completed / step.total!} label={`${step.label} ${counter}`} /><div className="step-meta">{counter}{step.elapsed_seconds !== undefined && <span>{step.elapsed_seconds.toFixed(1)}秒</span>}</div></>}
    {step.message && <span className="muted">{step.message}</span>}{step.error && <p className="error-text" role="alert">{step.error}</p>}
    {children.length > 0 && <div className="child-steps"><StepGroup steps={children} allSteps={steps} /></div>}
  </div>;
}
export function UploadSteps({ item }: { item: BatchItem }) {
  const uploads = item.upload?.uploads ?? [];
  const ended = uploads.filter((upload) => completed(upload.state) || upload.state === 'completed');
  const visible = uploads.filter((upload) => !ended.includes(upload));
  return <>{visible.map((upload) => <div className="upload-step" key={upload.key}>
    <strong>S3 上传 · {upload.key}</strong><span>{upload.state}</span>
    {upload.total_bytes > 0 && <Progress value={upload.transferred_bytes / upload.total_bytes} label="S3 上传字节进度" />}
    <span className="muted">{bytes(upload.transferred_bytes)} / {bytes(upload.total_bytes)}</span>
  </div>)}{ended.length > 0 && <Disclosure title={`已完成 S3 上传 · ${ended.length}`}>
    <ul>{ended.map((upload) => <li key={upload.key}>{upload.key} · {bytes(upload.transferred_bytes)}</li>)}</ul>
  </Disclosure>}</>;
}
