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

export function revealTimelinePosition(position: number, { width, scrollLeft, scrollWidth }: {
  width: number; scrollLeft: number; scrollWidth: number;
}): number {
  if (position >= scrollLeft && position < scrollLeft + width) return scrollLeft;
  return Math.max(0, Math.min(scrollWidth - width, position - width / 2));
}
