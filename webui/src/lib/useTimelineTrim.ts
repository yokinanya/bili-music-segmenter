'use client';
import { useEffect, useRef, useState, type PointerEvent, type RefObject } from 'react';
import type { SongClip } from './editor';
import { useTimelineAutoScroll } from './useTimelineAutoScroll';

const SNAP_DISTANCE_PX = 10;
const MILLISECONDS_PER_SECOND = 1000;
type Edge = 'start_seconds' | 'end_seconds';
interface Options {
  clips: SongClip[]; duration: number; time: number; scale: number; snapping: boolean;
  viewport: RefObject<HTMLDivElement | null>;
  position: (clientX: number) => number; onChange: (clips: SongClip[]) => void;
}
interface Session {
  pointerId: number; clip: SongClip; edge: Edge; origin: number; clips: SongClip[]; moved: boolean;
}
interface Preview { clip: SongClip; edge: Edge; snapTime: number | null }
interface Pointer { readonly clientX: number; readonly pointerId: number; readonly shiftKey: boolean }

function snapBoundary(input: { raw: number; active: Session; options: Options; shiftKey: boolean }): number | null {
  const { raw, active, options, shiftKey } = input;
  if (!options.snapping || shiftKey) return null;
  const candidates = [options.time, ...options.clips.filter(clip => clip.id !== active.clip.id)
    .flatMap(clip => [clip.start_seconds, clip.end_seconds])];
  const valid = candidates.filter(time => time >= 0 && time <= options.duration
    && (active.edge === 'start_seconds' ? time < active.clip.end_seconds : time > active.clip.start_seconds));
  return valid.reduce<number | null>((best, time) => {
    const distance = Math.abs(raw - time) * options.scale;
    return distance <= SNAP_DISTANCE_PX && (best === null || distance < Math.abs(raw - best) * options.scale) ? time : best;
  }, null);
}

export function useTimelineTrim(options: Options) {
  const session = useRef<Session | null>(null);
  const [preview, setPreview] = useState<Preview | null>(null);
  const autoScroll = useTimelineAutoScroll({ viewport: options.viewport, onFrame: pointer => update(pointer) });
  const cancel = () => { autoScroll.stop(); session.current = null; setPreview(null); };
  useEffect(() => {
    const escape = (event: KeyboardEvent) => {
      if (event.key !== 'Escape' || !session.current) return;
      event.preventDefault(); cancel();
    };
    window.addEventListener('keydown', escape);
    window.addEventListener('blur', cancel);
    return () => { window.removeEventListener('keydown', escape); window.removeEventListener('blur', cancel); };
  }, []);
  const calculate = (event: Pointer): Preview | null => {
    const active = session.current;
    if (!active || active.pointerId !== event.pointerId || active.clips !== options.clips) return null;
    const { clip, edge, origin } = active;
    const raw = clip[edge] + options.position(event.clientX) - origin;
    const snapTime = snapBoundary({ raw, active, options, shiftKey: event.shiftKey });
    const value = snapTime ?? Math.round(raw * MILLISECONDS_PER_SECOND) / MILLISECONDS_PER_SECOND;
    const bounded = Math.max(0, Math.min(options.duration, value));
    if (edge === 'start_seconds' ? bounded >= clip.end_seconds : bounded <= clip.start_seconds) return null;
    return { clip: { ...clip, [edge]: bounded }, edge, snapTime };
  };
  const update = (pointer: Pointer) => {
    const result = calculate(pointer);
    setPreview(result);
  };
  const finish = (event: PointerEvent<HTMLButtonElement>, commit: boolean) => {
    const active = session.current;
    if (!active || active.pointerId !== event.pointerId) return;
    event.stopPropagation();
    const result = commit && active.moved ? calculate(event) : null;
    cancel();
    if (event.currentTarget.hasPointerCapture(event.pointerId)) event.currentTarget.releasePointerCapture(event.pointerId);
    if (result && result.clip[active.edge] !== active.clip[active.edge]) {
      options.onChange(options.clips.map(clip => clip.id === result.clip.id ? result.clip : clip));
    }
  };
  const bind = (clip: SongClip, edge: Edge) => ({
    onPointerDown: (event: PointerEvent<HTMLButtonElement>) => {
      event.stopPropagation();
      if (event.button !== 0 || session.current) return;
      event.preventDefault();
      session.current = { pointerId: event.pointerId, clip, edge, origin: options.position(event.clientX), clips: options.clips, moved: false };
      event.currentTarget.setPointerCapture(event.pointerId);
      setPreview({ clip, edge, snapTime: null });
    },
    onPointerMove: (event: PointerEvent<HTMLButtonElement>) => {
      event.stopPropagation();
      if (session.current?.pointerId !== event.pointerId) return;
      session.current.moved = true;
      autoScroll.move(event); update(event);
    },
    onPointerUp: (event: PointerEvent<HTMLButtonElement>) => finish(event, true),
    onPointerCancel: (event: PointerEvent<HTMLButtonElement>) => finish(event, false),
    onLostPointerCapture: (event: PointerEvent<HTMLButtonElement>) => finish(event, false),
  });
  const visible = session.current?.clips === options.clips ? preview : null;
  return { bind, preview: visible, clips: options.clips.map(clip => clip.id === visible?.clip.id ? visible.clip : clip) };
}
