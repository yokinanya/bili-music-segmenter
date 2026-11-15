'use client';
import type { UsageSnapshot } from '@/lib/types';
import { Disclosure } from './Disclosure';
import { UsageSummary, money } from './UsageSummary';

/** Totals are cumulative across restarts, so the panel shows one scope: this machine. */
export function UsagePanel({ session }: { session: UsageSnapshot | null }) {
  return <>
    <div className="usage-cards">
      {session ? <UsageSummary usage={session} label="累计用量" /> : <section className="panel"><h2>累计用量</h2><p className="muted">正在读取…</p></section>}
    </div>
    <section className="panel model-panel">
      <Disclosure title="按模型明细" defaultOpen>
        {!session?.models.length && <p className="empty small-empty">暂无模型调用</p>}
        <ModelTable usage={session} />
      </Disclosure>
      <p className="helper">费用按官方价估算，实际以服务商账单为准。</p>
    </section>
  </>;
}
function ModelTable({ usage }: { usage: UsageSnapshot | null }) {
  if (!usage?.models.length) return null;
  return <div className="table-scroll"><table><caption>累计用量</caption>
    <thead><tr><th scope="col">模型</th><th scope="col">调用</th><th scope="col">输入</th><th scope="col">缓存</th><th scope="col">输出</th><th scope="col">估算费用</th></tr></thead>
    <tbody>{usage.models.map((row) => <tr key={row.model}>
      <td>{row.model}</td><td>{row.calls}</td><td>{row.input_tokens.toLocaleString()}</td>
      <td>{row.cached_tokens.toLocaleString()}</td><td>{row.output_tokens.toLocaleString()}</td><td>{money(row.estimated_usd)}</td>
    </tr>)}
    </tbody>
  </table></div>;
}
