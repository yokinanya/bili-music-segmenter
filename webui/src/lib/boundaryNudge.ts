import type { SongClip } from './editor';

export type BoundaryEdge = 'start_seconds' | 'end_seconds';
interface Options { edge: BoundaryEdge; delta: number; duration: number }
const MILLISECONDS = 1000;

export function nudgeBoundary(clip: SongClip, { edge, delta, duration }: Options): SongClip {
  const value = Math.round((clip[edge] + delta) * MILLISECONDS) / MILLISECONDS;
  const revised = { ...clip, [edge]: value };
  if (!Number.isFinite(value) || !Number.isFinite(duration) || revised.start_seconds < 0 || revised.start_seconds >= revised.end_seconds || revised.end_seconds > duration) {
    throw new Error('微调后的边界必须位于源视频内，且开头早于结尾');
  }
  return revised;
}
