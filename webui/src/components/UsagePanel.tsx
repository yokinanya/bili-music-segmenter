import type { UsageSnapshot } from '@/lib/types';

const PRICE_NOTE =
  '单价按 2026-10-20 官网截图：每百万 token 输入 ¥0.8、缓存输入 ¥0.1、输出 ¥2.7（两个模型相同）。仅估算，不含 S3 费用、免费额度和优惠；以官方账单为准。';

function money(value: number | null): string {
  return value === null ? '未知价格' : `¥${value.toFixed(6)}`;
}

function Summary({ usage, label }: { usage: UsageSnapshot; label: string }) {
  const note = usage.complete ? '' : '（统计不完整：存在缺失 usage 或未知价格模型）';
  return (
    <div className="usage-summary">
      <span className="usage-amount">{money(usage.estimated_cny)}</span>
      <span className="muted small">
        {label} · 输入 {usage.input_tokens.toLocaleString()} · 缓存命中 {usage.cached_tokens.toLocaleString()} · 输出{' '}
        {usage.output_tokens.toLocaleString()} token · {usage.calls} 次调用{note}
      </span>
    </div>
  );
}

export function UsagePanel({ session, job }: { session: UsageSnapshot | null; job: UsageSnapshot | null }) {
  return (
    <section className="card" aria-labelledby="usage-title">
      <div className="card-head">
        <h2 id="usage-title">用量与费用估算</h2>
      </div>
      {session ? <Summary usage={session} label="本次服务累计" /> : <p className="muted">正在读取统计…</p>}
      {job && <Summary usage={job} label="当前任务" />}
      <details className="usage-models">
        <summary>按模型明细</summary>
        <table>
          <thead>
            <tr>
              <th scope="col">模型</th>
              <th scope="col">调用</th>
              <th scope="col">输入</th>
              <th scope="col">缓存</th>
              <th scope="col">输出</th>
              <th scope="col">估算</th>
            </tr>
          </thead>
          <tbody>
            {(session?.models ?? []).map((row) => (
              <tr key={row.model}>
                <td>{row.model}</td>
                <td>{row.calls}</td>
                <td>{row.input_tokens.toLocaleString()}</td>
                <td>{row.cached_tokens.toLocaleString()}</td>
                <td>{row.output_tokens.toLocaleString()}</td>
                <td>{money(row.estimated_cny)}</td>
              </tr>
            ))}
            {(session?.models.length ?? 0) === 0 && (
              <tr>
                <td colSpan={6} className="muted">
                  暂无调用
                </td>
              </tr>
            )}
          </tbody>
        </table>
        <p className="muted small">{PRICE_NOTE}</p>
      </details>
    </section>
  );
}
