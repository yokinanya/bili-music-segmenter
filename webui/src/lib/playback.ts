export type PlayIntent = 'playing' | 'paused';

/**
 * Video element state as reported by browser events. `playing` is the only source of
 * truth for the play/pause button, so a pending play() that gets interrupted cannot
 * leave the UI showing the wrong state.
 */
export interface PlaybackState {
  readonly intent: PlayIntent;
  readonly time: number;
  readonly duration: number;
  readonly pending: boolean;
}

/** Initial playback view-model; updates return a new object. */
export const initialPlayback: PlaybackState = { intent: 'paused', time: 0, duration: 0, pending: false };

/** AbortError means a newer play()/pause() superseded this request, which is not a failure. */
export const isInterruption = (error: unknown): boolean =>
  error instanceof DOMException && error.name === 'AbortError';

/**
 * Clamp a scrub position. Dragging past either edge should stop at the boundary rather
 * than jump to 0 or report an out-of-range time to the element.
 */
export function scrubTime(value: number, duration: number): number {
  if (!Number.isFinite(duration) || duration <= 0) return 0;
  if (!Number.isFinite(value)) return 0;
  return Math.min(duration, Math.max(0, value));
}

/** Seek position for a pointer offset on a full-width scrub bar. */
export function scrubFromPointer(clientX: number, rect: { left: number; width: number }, duration: number): number {
  if (rect.width <= 0) return 0;
  return scrubTime((clientX - rect.left) / rect.width * duration, duration);
}

/** Time position of a command: 0..1 fraction of the track. */
export const progressFraction = (time: number, duration: number): number =>
  duration > 0 ? Math.min(1, Math.max(0, time / duration)) : 0;

