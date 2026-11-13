import type { BatchItem } from '@/lib/types';
import type { ProgressIssue, StepDetail } from '@/lib/progressSummary';
import { bytes, elapsed, progressCounter } from '@/lib/format';
import { StateBadge } from './StateBadge';
import { Disclosure } from './Disclosure';

const FRACTION_DIGITS = 1;

export function ProgressErrors({ issues }: { issues: readonly ProgressIssue[] }) {
  return <div className="progress-errors">{issues.map((issue) =>
    <div className="error progress-error" role="alert" key={issue.message}>
      <p className="error-sources">{issue.sources.join('、')}</p>
      <p className="error-message">{issue.message}</p>
    </div>)}</div>;
}

export function ProgressDetails({ steps }: { steps: readonly StepDetail[] }) {
  return <div hidden={!steps.length}><Disclosure title={`步骤详情 · ${steps.length}`} className="progress-details">
    <ol className="progress-records">
      {steps.map((detail) => <StepRecord key={detail.step.id} detail={detail} />)}
    </ol>
  </Disclosure></div>;
}

function StepRecord({ detail }: { detail: StepDetail }) {
  const { step, context } = detail;
  const counter = progressCounter(step);
  const duration = step.elapsed_seconds === undefined
    ? step.finished_at && elapsed(step.started_at, step.finished_at)
    : `${step.elapsed_seconds.toFixed(FRACTION_DIGITS)}秒`;
  return <li className="progress-record">
    <div className="progress-record-head"><strong>{step.label}</strong><StateBadge state={step.state} /></div>
    {context && <p className="muted progress-context">{context}</p>}
    <div className="progress-record-meta">
      {counter && <span>{counter}</span>}
      {duration && <span>{duration}</span>}
      {step.waiting_seconds !== undefined && step.waiting_seconds > 0 &&
        <span>等待资源 {step.waiting_seconds.toFixed(FRACTION_DIGITS)}秒</span>}
    </div>
    {step.message && <p className="muted progress-message">{step.message}</p>}
    {step.error && <p className="error-text progress-message">{step.error}</p>}
  </li>;
}
