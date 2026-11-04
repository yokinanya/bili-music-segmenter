import type { UsageSnapshot } from '@/lib/types';
export function money(value: number | null) {
  return value === null ? '价格未知' : `¥${value.toFixed(6)}`;
}
export function UsageSummary({ usage, label }: { usage: UsageSnapshot | null; label: string }) {
  return <article className="panel usage-summary"><h2>{label}</h2>
    {usage ? <><strong className="usage-amount">{money(usage.estimated_cny)}</strong>
      <dl className="usage-stats"><div><dt>模型调用</dt><dd>{usage.calls}</dd></div>
        <div><dt>输入 token</dt><dd>{usage.input_tokens.toLocaleString()}</dd></div>
        <div><dt>缓存 token</dt><dd>{usage.cached_tokens.toLocaleString()}</dd></div>
        <div><dt>输出 token</dt><dd>{usage.output_tokens.toLocaleString()}</dd></div></dl>
      {!usage.complete && <p className="error-text">统计不完整：部分调用缺少用量或价格。</p>}
    </> : <p className="muted">未选择任务</p>}
  </article>;
}
