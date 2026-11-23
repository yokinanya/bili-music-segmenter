export const ZOOM_STEPS = [1, 2, 4, 8, 16, 32];

interface ZoomPosition { zoom: number; scrollLeft: number }
interface Options { element: HTMLElement; zoom: number; onZoom: (position: ZoomPosition) => void }

export function bindPageZoomPrevention(target: Document) {
  const wheel = (event: WheelEvent) => {
    if (event.ctrlKey) event.preventDefault();
  };
  target.addEventListener('wheel', wheel, { capture: true, passive: false });
  return () => target.removeEventListener('wheel', wheel, { capture: true });
}

export function bindTimelineZoom({ element, zoom, onZoom }: Options) {
  let pending: ZoomPosition | null = null;
  const wheel = (event: WheelEvent) => {
    if (!(event.ctrlKey || event.metaKey) || event.deltaY === 0) return;
    event.preventDefault();
    const current = pending?.zoom ?? zoom;
    const direction = event.deltaY < 0 ? 1 : -1;
    const index = Math.max(0, Math.min(ZOOM_STEPS.length - 1, ZOOM_STEPS.indexOf(current) + direction));
    const next = ZOOM_STEPS[index];
    if (next === current) return;
    const bounds = element.getBoundingClientRect();
    const pointer = Math.max(0, Math.min(bounds.width, event.clientX - bounds.left));
    const scroll = pending?.scrollLeft ?? element.scrollLeft;
    pending = { zoom: next, scrollLeft: Math.max(0, (scroll + pointer) * next / current - pointer) };
    onZoom(pending);
  };
  element.addEventListener('wheel', wheel, { passive: false });
  return () => element.removeEventListener('wheel', wheel);
}
