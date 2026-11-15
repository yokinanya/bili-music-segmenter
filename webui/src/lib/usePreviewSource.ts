'use client';
import { useEffect, useRef, type RefObject } from 'react';
import { attachPreview, type PreviewSource } from './previewMedia';

export function usePreviewSource(video: RefObject<HTMLVideoElement | null>, source: PreviewSource) {
  const { src, type, duration, onError } = source;
  const report = useRef(onError);
  report.current = onError;
  useEffect(() => {
    const element = video.current;
    if (!element || !src) return;
    let active = true;
    let dispose: (() => void) | undefined;
    const options = { video: element, src, type, duration, onError: (message: string) => report.current(message) };
    if (type !== 'flv') dispose = attachPreview(options);
    else void import('mpegts.js').then(module => {
      if (active) dispose = attachPreview(options, module.default);
    }).catch((error: unknown) => {
      if (active) report.current(error instanceof Error ? error.message : String(error));
    });
    return () => { active = false; dispose?.(); };
  }, [video, src, type, duration]);
}
