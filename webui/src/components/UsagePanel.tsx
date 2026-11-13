'use client';
import { useState } from 'react';
import type { UsageSnapshot } from '@/lib/types';
import { Tabs } from './Material';
import { Disclosure } from './Disclosure';
import { UsageSummary, money } from './UsageSummary';

export function UsagePanel({ session, job }: { session: UsageSnapshot | null; job: UsageSnapshot | null }) {
  const [scope, setScope] = useState('选中任务');
  const usage = scope === '本次服务' ? session : job;
  return <>
    <div className="usage-cards">
      {session ? <UsageSummary usage={session} label="本次服务" /> : <section className="panel"><h2>本次服务</h2><p className="muted">正在读取…</p></section>}
      <UsageSummary usage={job} label="选中任务" />
    </div>
    <section className="panel model-panel">
      <Disclosure title="按模型明细" defaultOpen>
        <Tabs value={scope} options={['选中任务', '本次服务']} onChange={setScope} label="模型用量范围" />
        {!usage?.models.length && <p className="empty small-empty">{scope === '选中任务' && !job ? '选择任务以查看模型明细' : '暂无模型调用'}</p>}
        <ModelTable label={scope} usage={usage} />
      </Disclosure>
      <p className="helper">费用按官方价估算，实际以服务商账单为准。</p>
    </section>
  </>;
}
function ModelTable({ label, usage }: { label: string; usage: UsageSnapshot | null }) {
  if (!usage?.models.length) return null;
  return <div className="table-scroll"><table><caption>{label}</caption>
    <thead><tr><th scope="col">模型</th><th scope="col">调用</th><th scope="col">输入</th><th scope="col">缓存</th><th scope="col">输出</th><th scope="col">估算费用</th></tr></thead>
    <tbody>{usage?.models.map((row) => <tr key={row.model}>
      <td>{row.model}</td><td>{row.calls}</td><td>{row.input_tokens.toLocaleString()}</td>
      <td>{row.cached_tokens.toLocaleString()}</td><td>{row.output_tokens.toLocaleString()}</td><td>{money(row.estimated_cny)}</td>
    </tr>)}
    </tbody>
  </table></div>;
}
