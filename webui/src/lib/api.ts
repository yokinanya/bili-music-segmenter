import type { Bootstrap, HistoryEntry, InputFile, JobStatus, LogChunk, UsageSnapshot } from './types';

const TOKEN_KEY = 'bms-token';

export class ApiError extends Error {
  readonly status: number;
  readonly retryable: boolean;

  constructor(message: string, status: number) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    // Network failures and server errors are worth retrying; 4xx are user or input errors.
    this.retryable = status === 0 || status >= 500;
  }
}

function readTokenFromUrl(): string | null {
  const params = new URLSearchParams(window.location.search);
  const token = params.get('token');
  // Persist so a reload without the query string still works.
  if (!token) return window.localStorage.getItem(TOKEN_KEY);
  window.localStorage.setItem(TOKEN_KEY, token);
  // Keep the token out of the address bar and out of copied links.
  params.delete('token');
  const query = params.toString();
  window.history.replaceState(null, '', `${window.location.pathname}${query ? `?${query}` : ''}`);
  return token;
}

export const token = typeof window === 'undefined' ? null : readTokenFromUrl();

async function request<T>(url: string, init: RequestInit = {}, timeoutMs = 15000): Promise<T> {
  const controller = new AbortController();
  const timer = window.setTimeout(() => controller.abort(), timeoutMs);
  try {
    const response = await fetch(url, {
      ...init,
      signal: controller.signal,
      headers: { 'Content-Type': 'application/json', 'X-WebUI-Token': token ?? '', ...(init.headers ?? {}) },
    });
    const text = await response.text();
    const data = text ? (JSON.parse(text) as Record<string, unknown>) : {};
    if (!response.ok) {
      const message = typeof data.error === 'string' ? data.error : `请求失败（HTTP ${response.status}）`;
      throw new ApiError(message, response.status);
    }
    return data as T;
  } catch (cause) {
    if (cause instanceof ApiError) throw cause;
    if (cause instanceof DOMException && cause.name === 'AbortError') {
      throw new ApiError('请求超时，请确认本地服务仍在运行', 0);
    }
    throw new ApiError('无法连接本地服务', 0);
  } finally {
    window.clearTimeout(timer);
  }
}

export const api = {
  bootstrap: () => request<Bootstrap>('/api/bootstrap'),
  inputs: () => request<{ directory: string; files: InputFile[] }>('/api/inputs'),
  usage: () => request<UsageSnapshot>('/api/usage'),
  history: () => request<{ entries: HistoryEntry[] }>('/api/history'),
  job: (id: string) => request<JobStatus>(`/api/jobs/${encodeURIComponent(id)}`),
  start: (media: string[], outdir: string) =>
    request<{ id: string }>('/api/jobs', { method: 'POST', body: JSON.stringify({ media, outdir }) }, 30000),
  stop: (id: string) =>
    request<{ stopped: boolean }>(`/api/jobs/${encodeURIComponent(id)}/stop`, { method: 'POST', body: '{}' }),
  log: (id: string, item: number, offset: number) =>
    request<LogChunk>(`/api/jobs/${encodeURIComponent(id)}/log`, {
      headers: { 'X-Log-Item': String(item), 'X-Log-Offset': String(offset) },
    }),
};

/** <video> cannot send headers, so the download URL carries the same per-launch token. */
export function clipUrl(jobId: string, clipName: string, download = false): string {
  const query = new URLSearchParams({ token: token ?? '' });
  if (download) query.set('download', '1');
  return `/api/jobs/${encodeURIComponent(jobId)}/clip/${encodeURIComponent(clipName)}?${query}`;
}
