import type { JobStatus, ModelUsage, UsageSnapshot } from '@/lib/types';

interface TokenUsage {
  prompt_tokens?: number; completion_tokens?: number;
  prompt_tokens_details?: { cached_tokens?: number };
  total_input_tokens?: number; total_output_tokens?: number; total_cached_tokens?: number;
}
const MILLION = 1_000_000;
// Same per-million USD rates as segment/usage.py; unknown models remain unpriced.
const PRICES: Readonly<Record<string, readonly number[]>> = {
  'gemini-4-hydrogen': [1.5, 0.075, 7.5], 'gemini-4-argon': [2, 0.1, 10],
  'gemini-4-carbon': [2, 0.1, 10], 'gemini-3.8-flash': [0.75, 0.075, 3.75],
  'gemini-3.6-flash': [0.75, 0.075, 3.75], 'gemini-3.5-flash-lite': [0.75, 0.075, 3.75],
};
function tokens(value: unknown): TokenUsage {
  if (!value || typeof value !== 'object') throw new Error('模型 usage 格式无效');
  const usage = value as TokenUsage;
  const values: Array<number | undefined> = [
    usage.total_input_tokens ?? usage.prompt_tokens,
    usage.total_output_tokens ?? usage.completion_tokens,
    usage.total_cached_tokens ?? usage.prompt_tokens_details?.cached_tokens ?? 0,
  ];
  if (values.some((count) => !Number.isInteger(count) || (count as number) < 0) || (values[2] as number) > (values[0] as number)) throw new Error('模型 usage token 数值无效');
  return usage;
}
function accumulate(row: ModelUsage, value: unknown): ModelUsage {
  if (value === null) return { ...row, calls: row.calls + 1, missing_usage: row.missing_usage + 1 };
  const usage = tokens(value);
  const prompt = usage.total_input_tokens ?? usage.prompt_tokens ?? 0;
  const completion = usage.total_output_tokens ?? usage.completion_tokens ?? 0;
  const cached = usage.total_cached_tokens ?? usage.prompt_tokens_details?.cached_tokens ?? 0;
  const price = Object.hasOwn(PRICES, row.model) ? PRICES[row.model] : undefined;
  const cost = price ? ((prompt - cached) * price[0] + cached * price[1] + completion * price[2]) / MILLION : null;
  return { ...row, calls: row.calls + 1, input_tokens: row.input_tokens + prompt,
    cached_tokens: row.cached_tokens + cached, output_tokens: row.output_tokens + completion,
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
