export function timelineTickAlignment(index: number, count: number): 'start' | 'center' | 'end' {
  if (index === 0) return 'start';
  if (index === count - 1) return 'end';
  return 'center';
}

export function timelineTickTranslation(index: number, count: number): string {
  const alignment = timelineTickAlignment(index, count);
  return alignment === 'start' ? '0' : alignment === 'end' ? '-100%' : '-50%';
}

export function timelineWidth(viewportWidth: number, zoom: number): number {
  return Math.max(0, viewportWidth) * Math.max(1, zoom);
}
