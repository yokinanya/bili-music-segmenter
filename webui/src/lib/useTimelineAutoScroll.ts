'use client';
import { useLayoutEffect, useRef, type RefObject } from 'react';

const EDGE_ZONE_PX = 40;
const MAX_SPEED_PX_PER_SECOND = 600;
const MILLISECONDS_PER_SECOND = 1000;
interface Pointer { readonly clientX: number; readonly shiftKey: boolean; readonly pointerId: number }
interface Options { viewport: RefObject<HTMLDivElement | null>; onFrame: (pointer: Pointer) => void }

export function useTimelineAutoScroll(options: Options) {
  const latest = useRef(options), pointer = useRef<Pointer | null>(null);
  const frame = useRef<number | null>(null), previous = useRef<number | null>(null);
  useLayoutEffect(() => { latest.current = options; });
  const stop = () => {
    if (frame.current !== null) cancelAnimationFrame(frame.current);
    frame.current = null; previous.current = null; pointer.current = null;
  };
  useLayoutEffect(() => stop, []);
  const tick = (now: number) => {
    const element = latest.current.viewport.current, sample = pointer.current;
    if (!element || !sample) { stop(); return; }
    const elapsed = previous.current === null ? 0 : (now - previous.current) / MILLISECONDS_PER_SECOND;
    previous.current = now;
    const bounds = element.getBoundingClientRect();
    const left = Math.max(0, Math.min(1, (bounds.left + EDGE_ZONE_PX - sample.clientX) / EDGE_ZONE_PX));
    const right = Math.max(0, Math.min(1, (sample.clientX - bounds.right + EDGE_ZONE_PX) / EDGE_ZONE_PX));
    const before = element.scrollLeft;
    element.scrollLeft += (right - left) * MAX_SPEED_PX_PER_SECOND * elapsed;
    if (element.scrollLeft !== before) latest.current.onFrame(sample);
    frame.current = requestAnimationFrame(tick);
  };
  const move = (sample: Pointer) => {
    pointer.current = { clientX: sample.clientX, shiftKey: sample.shiftKey, pointerId: sample.pointerId };
    if (frame.current === null) frame.current = requestAnimationFrame(tick);
  };
  return { move, stop };
}
