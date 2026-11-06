import type { JobStatus, ModelUsage, UsageSnapshot } from '@/lib/types';

interface TokenUsage { prompt_tokens: number; completion_tokens: number; prompt_tokens_details?: { cached_tokens?: number } }
const MILLION = 1_000_000;
// Same per-million CNY rates as segment/usage.py; unknown models remain unpriced.
const PRICES: Readonly<Record<string, readonly number[]>> = {
  'qwen3.8-flash': [0.8, 0.1, 2.7], 'qwen3.8-omni-flash': [0.8, 0.1, 2.7],
};
function tokens(value: unknown): TokenUsage {
  if (!value || typeof value !== 'object') throw new Error('模型 usage 格式无效');
  const usage = value as TokenUsage;
  const values = [usage.prompt_tokens, usage.completion_tokens, usage.prompt_tokens_details?.cached_tokens ?? 0];
  if (values.some((count) => !Number.isInteger(count) || count < 0) || values[2] > values[0]) throw new Error('模型 usage token 数值无效');
  return usage;
}
function accumulate(row: ModelUsage, value: unknown): ModelUsage {
  if (value === null) return { ...row, calls: row.calls + 1, missing_usage: row.missing_usage + 1 };
  const usage = tokens(value), cached = usage.prompt_tokens_details?.cached_tokens ?? 0;
  const price = Object.hasOwn(PRICES, row.model) ? PRICES[row.model] : undefined;
  const cost = price ? ((usage.prompt_tokens - cached) * price[0] + cached * price[1] + usage.completion_tokens * price[2]) / MILLION : null;
  return { ...row, calls: row.calls + 1, input_tokens: row.input_tokens + usage.prompt_tokens,
    cached_tokens: row.cached_tokens + cached, output_tokens: row.output_tokens + usage.completion_tokens,
    estimated_cny: cost === null ? null : (row.estimated_cny ?? 0) + cost };
}
export function attemptUsage(job: JobStatus): UsageSnapshot {
  const models = job.usage_events.filter((event) => event.attempt === job.attempt).reduce<Record<string, ModelUsage>>((rows, event) => {
    const row = Object.hasOwn(rows, event.model) ? rows[event.model] : { model: event.model, calls: 0, missing_usage: 0, input_tokens: 0, output_tokens: 0, cached_tokens: 0, estimated_cny: 0 };
    return { ...rows, [event.model]: accumulate(row, event.usage) };
  }, {});
  const rows = Object.values(models);
  return { models: rows, calls: rows.reduce((sum, row) => sum + row.calls, 0),
    input_tokens: rows.reduce((sum, row) => sum + row.input_tokens, 0),
    output_tokens: rows.reduce((sum, row) => sum + row.output_tokens, 0),
    cached_tokens: rows.reduce((sum, row) => sum + row.cached_tokens, 0),
    estimated_cny: rows.reduce((sum, row) => sum + (row.estimated_cny ?? 0), 0),
    complete: rows.every((row) => !row.missing_usage && row.estimated_cny !== null) };
}
