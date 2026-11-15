export interface SongClip {
  readonly id: string; readonly start_seconds: number; readonly end_seconds: number;
  readonly title: string; readonly artist: string; readonly name: string;
  readonly recognition?: unknown; readonly title_resolution?: unknown;
}
export interface EditorProject {
  readonly id: string; readonly revision: number; readonly upload_id: string;
  readonly name: string; readonly duration: number; readonly clips: SongClip[];
}
export interface EditHistory { readonly past: SongClip[][]; readonly present: SongClip[]; readonly future: SongClip[][] }
type EditAction = { type: 'replace' | 'open'; clips: SongClip[] } | { type: 'undo' | 'redo' };

export function splitClip(clip: SongClip, time: number, identity: string): SongClip[] {
  if (!Number.isFinite(time) || time <= clip.start_seconds || time >= clip.end_seconds) throw new Error('拆分点必须位于片段内部');
  return [{ ...clip, end_seconds: time }, { ...clip, id: identity, start_seconds: time }];
}
export function mergeClips(clips: SongClip[]): SongClip {
  if (clips.length < 2) throw new Error('请选择至少两个片段');
  return { ...clips[0], start_seconds: Math.min(...clips.map(c => c.start_seconds)), end_seconds: Math.max(...clips.map(c => c.end_seconds)) };
}
export function updateSongTitle(clip: SongClip, title: string): SongClip {
  const safe = title.replace(/[\\/:*?"<>|\x00-\x1f]/g, ' ').replace(/\s+/g, ' ').trim().replace(/[. ]+$/g, '');
  const basename = /^(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\.|$)/i.test(safe) ? `_${safe}` : safe;
  return { ...clip, title, name: `${basename || 'song'}.mp4` };
}
export function timeAt(input: { x: number; left: number; scroll: number; pixelsPerSecond: number; duration: number }): number {
  return Math.max(0, Math.min(input.duration, (input.x - input.left + input.scroll) / input.pixelsPerSecond));
}
export function editHistory(state: EditHistory, action: EditAction): EditHistory {
  if (action.type === 'open') return { past: [], present: action.clips, future: [] };
  if (action.type === 'replace') return { past: [...state.past, state.present], present: action.clips, future: [] };
  if (action.type === 'undo' && state.past.length) return { past: state.past.slice(0, -1), present: state.past[state.past.length - 1], future: [state.present, ...state.future] };
  if (action.type === 'redo' && state.future.length) return { past: [...state.past, state.present], present: state.future[0], future: state.future.slice(1) };
  return state;
}

/** Deleting a source must also drop the open draft when that draft was the deleted one. */
export function removeProject(
  projects: readonly EditorProject[],
  removedId: string,
  openId: string | null,
): { projects: EditorProject[]; openId: string | null } {
  const remaining = projects.filter((value) => value.id !== removedId);
  if (removedId !== openId) return { projects: remaining, openId };
  return { projects: remaining, openId: remaining[0]?.id ?? null };
}
