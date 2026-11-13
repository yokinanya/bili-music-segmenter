import type { BatchItem, JobState, JobStatus, ProgressStep } from './types';

const ACTIVE_JOB_STATES = new Set<JobState>(['queued', 'running']);
const ACTIVE_STEP_STATES = new Set(['running', 'waiting', 'retrying']);
const COUNTER_STEP_IDS = new Set(['prepare', 'finalize']);
const BATCH_ISSUES = [
  { state: 'failed', label: '失败' },
  { state: 'cancelled', label: '已停止' },
  { state: 'interrupted', label: '已中断' },
  { state: 'cleanup_pending', label: '清理未完成' },
] as const;

type ProgressJob = Pick<JobStatus, 'state' | 'attempt' | 'error' | 'cleanup_error'>;

export interface ProgressMeasurement {
  readonly label: string;
  readonly completed: number;
  readonly total: number;
  readonly unit: string | null;
}

export interface StepDetail {
  readonly step: ProgressStep;
  readonly ancestors: readonly ProgressStep[];
  readonly context: string;
  readonly measurement: ProgressMeasurement | null;
}

export interface ProgressIssue {
  readonly message: string;
  readonly sources: readonly string[];
}

function ancestorsOf(step: ProgressStep, index: ReadonlyMap<string, ProgressStep>) {
  const ancestors: ProgressStep[] = [];
  const visited = new Set([step.id]);
  let parent = step.parent_id ? index.get(step.parent_id) : undefined;
  while (parent) {
    if (visited.has(parent.id)) throw new Error(`步骤层级存在循环：${parent.id}`);
    ancestors.push(parent);
    visited.add(parent.id);
    parent = parent.parent_id ? index.get(parent.parent_id) : undefined;
  }
  return ancestors;
}

function measurementOf(steps: readonly ProgressStep[]): ProgressMeasurement | null {
  const measured = steps.find((step) => step.total !== null && step.total > 0);
  if (!measured || measured.total === null) return null;
  return { label: measured.label, completed: measured.completed, total: measured.total, unit: measured.unit };
}

function describeSteps(steps: readonly ProgressStep[]) {
  const index = new Map(steps.map((step) => [step.id, step]));
  return steps.map((step): StepDetail => {
    const ancestors = ancestorsOf(step, index);
    return {
      step,
      ancestors,
      context: [...ancestors].reverse().map((parent) => parent.label).join(' · '),
      measurement: measurementOf([step]),
    };
  });
}

function currentWork(details: readonly StepDetail[], attempt: number) {
  const active = details.filter(({ step }) =>
    step.attempt === attempt && ACTIVE_STEP_STATES.has(step.state) && !COUNTER_STEP_IDS.has(step.id));
  const parents = new Set(active.flatMap(({ ancestors }) => ancestors.map((parent) => parent.id)));
  const leaves = active.filter(({ step }) => !parents.has(step.id));
  let current: StepDetail | null = null;
  for (const detail of leaves) {
    if (!current || detail.step.sequence >= current.step.sequence) current = detail;
  }
  return { current, parallelCount: Math.max(0, leaves.length - 1) };
}

/** 父步骤与子步骤同名时只保留一次，避免「导出片段 · 导出片段」。 */
function pathOf(current: StepDetail | null): string {
  if (!current) return '';
  const labels = [...current.ancestors].reverse().map((parent) => parent.label);
  labels.push(current.step.label);
  return labels.filter((label, index) => label && label !== labels[index - 1]).join(' · ');
}

/** 计数器只在路径没有提到该标签时补前缀，否则同一行会重复同一步骤名。 */
function prefixOf(measurement: ProgressMeasurement | null, path: string): string {
  if (!measurement) return '';
  // 按路径分段精确比较：子串判断会让「片段」命中「导出片段」。
  return path.split(' · ').includes(measurement.label) ? '' : `${measurement.label} · `;
}

function runningProgress(details: readonly StepDetail[], attempt: number) {
  const { current, parallelCount } = currentWork(details, attempt);
  const measurement = current ? measurementOf([current.step, ...current.ancestors]) : null;
  const path = pathOf(current);
  return { current, parallelCount, measurement, path, counterPrefix: prefixOf(measurement, path) };
}

function progressIssues({ job, item, details }: {
  readonly job: ProgressJob;
  readonly item: BatchItem;
  readonly details: readonly StepDetail[];
}): readonly ProgressIssue[] {
  const records = [
    { source: '任务', message: job.error },
    { source: '任务清理', message: job.cleanup_error },
    { source: item.media, message: item.error },
    ...details.map(({ step, context }) => ({
      source: context ? `${context} · ${step.label}` : step.label,
      message: step.error || (step.state === 'failed' ? '步骤执行失败，尚无错误详情' : null),
    })),
  ];
  const grouped = new Map<string, Set<string>>();
  for (const { source, message } of records) {
    if (!message) continue;
    const sources = grouped.get(message) ?? new Set<string>();
    sources.add(source);
    grouped.set(message, sources);
  }
  return [...grouped].map(([message, sources]) => ({ message, sources: [...sources] }));
}

export function summarizeProgress({ job, item }: { readonly job: ProgressJob; readonly item: BatchItem }) {
  const details = describeSteps(item.steps);
  const state = ACTIVE_JOB_STATES.has(item.state) && !ACTIVE_JOB_STATES.has(job.state) ? job.state : item.state;
  const running = state === 'running';
  const progress = running
    ? runningProgress(details, job.attempt)
    : { current: null, parallelCount: 0, measurement: null, path: '', counterPrefix: '' };
  return {
    state,
    running,
    ...progress,
    details,
    issues: progressIssues({ job, item, details }),
    unprocessed: item.state === 'queued' && !ACTIVE_JOB_STATES.has(job.state),
  };
}

export function summarizeBatch(batch: readonly BatchItem[]) {
  const counts = new Map<JobState, number>();
  for (const item of batch) counts.set(item.state, (counts.get(item.state) ?? 0) + 1);
  return {
    ended: batch.filter((item) => !ACTIVE_JOB_STATES.has(item.state)).length,
    issues: BATCH_ISSUES.map(({ state, label }) => ({ label, count: counts.get(state) ?? 0 }))
      .filter(({ count }) => count > 0),
  };
}

