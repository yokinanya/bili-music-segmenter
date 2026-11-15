'use client';
import { useRef, type PointerEvent } from 'react';

interface Options {
  readonly onSeek: (clientX: number) => void;
  readonly onStart?: () => void;
  readonly onEnd?: () => void;
  readonly enabled: boolean;
}

export function usePointerSeek({ onSeek, onStart, onEnd, enabled }: Options) {
  const pointer = useRef<number | null>(null);
  const finish = (event: PointerEvent<HTMLElement>, seek: boolean) => {
    if (pointer.current !== event.pointerId) return;
    pointer.current = null;
    if (seek) onSeek(event.clientX);
    if (event.currentTarget.hasPointerCapture(event.pointerId)) event.currentTarget.releasePointerCapture(event.pointerId);
    onEnd?.();
  };
  return {
    onPointerDown: (event: PointerEvent<HTMLElement>) => {
      if (!enabled || event.button !== 0 || pointer.current !== null) return;
      event.preventDefault();
      pointer.current = event.pointerId;
      event.currentTarget.setPointerCapture(event.pointerId);
      onStart?.();
      onSeek(event.clientX);
    },
    onPointerMove: (event: PointerEvent<HTMLElement>) => {
      if (pointer.current === event.pointerId) onSeek(event.clientX);
    },
    onPointerUp: (event: PointerEvent<HTMLElement>) => finish(event, true),
    onPointerCancel: (event: PointerEvent<HTMLElement>) => finish(event, false),
    onLostPointerCapture: (event: PointerEvent<HTMLElement>) => finish(event, false),
  };
}
