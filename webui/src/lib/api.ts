import type { Bootstrap, HistoryEntry, JobStatus, LogChunk, RunOptions, SourceAsset, UsageSnapshot } from './types';
const TOKEN_KEY = 'bms-token';
function readToken(): string {
  const url = new URL(window.location.href);
  const value = url.searchParams.get('token');
  if (!value) return localStorage.getItem(TOKEN_KEY) ?? '';
  localStorage.setItem(TOKEN_KEY, value);
  url.searchParams.delete('token');
  window.history.replaceState(null, '', url.pathname + url.search + url.hash);
  return value;
}
export const token = typeof window === 'undefined' ? '' : readToken();
async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const response = await fetch(path, { ...init, headers: { 'Content-Type': 'application/json', 'X-WebUI-Token': token, ...init.headers } });
  const data = await response.json();
  if (!response.ok) throw new Error(data.error ?? `请求失败：${response.status}`);
  return data as T;
}
const post = <T>(path: string, data: unknown = {}) => request<T>(path, { method: 'POST', body: JSON.stringify(data) });
export const api = {
  bootstrap: () => request<Bootstrap>('/api/bootstrap'),
  uploads: () => request<{ files: SourceAsset[] }>('/api/uploads'),
  register: (file: File) => post<SourceAsset>('/api/uploads', { name: file.name, size_bytes: file.size }),
  removeUpload: (id: string) => request(`/api/uploads/${id}`, { method: 'DELETE' }),
  job: (id: string) => request<JobStatus>(`/api/jobs/${id}`),
  start: (upload_ids: string[], options: RunOptions, request_id: string) => post<{ id: string }>('/api/jobs', { upload_ids, options, request_id }),
  download: (payload: { url: string; cookie: string; options: RunOptions; request_id: string }) => post<{ id: string }>('/api/downloads', payload),
  stop: (id: string) => post(`/api/jobs/${id}/stop`),
  retry: (id: string) => post<{ id: string }>(`/api/jobs/${id}/retry`),
  delete: (id: string) => request(`/api/jobs/${id}`, { method: 'DELETE' }),
  history: () => request<{ entries: HistoryEntry[] }>('/api/history'),
  usage: () => request<UsageSnapshot>('/api/usage'),
  log: (id: string, index: number, offset: number) => request<LogChunk>(`/api/jobs/${id}/log`, { headers: { 'X-Log-Item': String(index), 'X-Log-Offset': String(offset) } }),
};
export function downloadUrl(id: string, action: string, download = false): string {
  return `/api/jobs/${id}/${action}?${new URLSearchParams({ token, ...(download ? { download: '1' } : {}) })}`;
}
export const clipUrl = (job: string, clip: string, download = false) => downloadUrl(job, `clip/${clip}`, download);
export function transfer(source: SourceAsset, file: File, { update, signal }: { update: (bytes: number) => void; signal: AbortSignal }): Promise<SourceAsset> {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    const abort = () => xhr.abort();
    const finish = () => signal.removeEventListener('abort', abort);
    xhr.open('PUT', `/api/uploads/${source.id}`);
    xhr.setRequestHeader('X-WebUI-Token', token);
    xhr.upload.onprogress = (event) => update(event.loaded);
    xhr.onerror = () => { finish(); reject(new Error('文件上传连接失败，请重试')); };
    xhr.onabort = () => { finish(); reject(new DOMException('上传已取消', 'AbortError')); };
    xhr.onload = () => {
      finish();
      try {
        const data = JSON.parse(xhr.responseText);
        if (xhr.status !== 200) throw new Error(data.error ?? '上传失败');
        resolve(data);
      } catch (error) { reject(error); }
    };
    signal.addEventListener('abort', abort, { once: true });
    if (signal.aborted) { finish(); reject(new DOMException('上传已取消', 'AbortError')); return; }
    xhr.send(file);
  });
}
