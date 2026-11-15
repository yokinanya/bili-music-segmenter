import type { SongClip } from './editor';
import type { ExportTask } from './editorApi';

export function exportFilename(name: string, suffix: string): string {
  const dot = name.lastIndexOf('.');
  return dot > 0 ? `${name.slice(0, dot)}${suffix}${name.slice(dot)}` : `${name}${suffix}`;
}

export function matchesExport(task: ExportTask, clips: readonly SongClip[], suffix = ''): boolean {
  if ((task.filename_suffix ?? '') !== suffix) return false;
  if (task.clips.length !== clips.length) return false;
  return task.clips.every(item => clips.some(clip => clip.id === item.id && exportFilename(clip.name, suffix) === item.name
    && clip.start_seconds === item.start_seconds && clip.end_seconds === item.end_seconds));
}
