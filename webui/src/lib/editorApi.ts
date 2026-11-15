import { token } from './api';
import type { EditorProject, SongClip } from './editor';
export interface Waveform { seconds_per_peak: number; peaks: number[] }
export interface ExportTask { id: string; revision: number; state: string; completed: number; error: string | null; progress: { completed_seconds: number; total_seconds: number } | null; clips: (SongClip & { path?: string })[]; cancel_requested?: boolean; filename_suffix?: string }
async function send<T>(path: string, method = 'GET', body?: unknown): Promise<T> {
  const response = await fetch(`/api/projects${path}`, { method, headers: { 'X-WebUI-Token': token, 'Content-Type': 'application/json' }, body: body === undefined ? undefined : JSON.stringify(body) });
  const data = await response.json();
  if (!response.ok) throw new Error(data.error ?? `请求失败：${response.status}`);
  return data;
}
export const editorApi = {
  list: () => send<{ projects: EditorProject[] }>(''),
  create: (upload_id: string) => send<EditorProject>('', 'POST', { upload_id }),
  get: (id: string) => send<EditorProject>(`/${id}`),
  save: (project: EditorProject, clips: SongClip[]) => send<EditorProject>(`/${project.id}`, 'PUT', { revision: project.revision, clips }),
  remove: (id: string) => send<{ deleted: string }>(`/${id}`, 'DELETE'),
  waveform: (id: string) => send<Waveform>(`/${id}/waveform`),
  analyze: (project: string, options: import('./types').RunOptions, refresh = false) => send<{ id: string }>(`/${project}/analyze`, 'POST', { options, refresh }),
  candidates: (project: string, job: string) => send<{ clips: SongClip[]; state: string; error: string | null }>(`/${project}/analysis/${job}`),
  export: (project: EditorProject, clip_ids: string[], filename_suffix = '') => send<ExportTask>(`/${project.id}/exports`, 'POST', { revision: project.revision, clip_ids, filename_suffix }),
  exportStatus: (project: string, task: string) => send<ExportTask>(`/${project}/exports/${task}`),
  exports: (project: string) => send<{ tasks: ExportTask[] }>(`/${project}/exports`),
  cancelExport: (project: string, task: string) => send<ExportTask>(`/${project}/exports/${task}/cancel`, 'POST', {}),
};
export const sourceUrl = (id: string) => `/api/projects/${id}/source?${new URLSearchParams({ token })}`;
export const exportUrl = (project: string, task: string, action: string) => `/api/projects/${project}/exports/${task}/${action}?${new URLSearchParams({ token })}`;
