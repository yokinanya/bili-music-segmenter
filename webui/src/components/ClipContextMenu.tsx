'use client';
import { useEffect, useLayoutEffect, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { Icon } from './Icon';

export interface ClipMenuPosition { x: number; y: number; ids: string[] }
interface Props {
  position: ClipMenuPosition; onClose: () => void;
  onDelete: (ids: string[]) => void; onMerge: (ids: string[]) => void;
}
export function ClipContextMenu({ position, onClose, onDelete, onMerge }: Props) {
  const ref = useRef<HTMLDivElement>(null);
  const [point, setPoint] = useState({ x: position.x, y: position.y });
  useLayoutEffect(() => {
    const menu = ref.current;
    if (!menu) return;
    const margin = 8;
    setPoint({ x: Math.max(margin, Math.min(position.x, innerWidth - menu.offsetWidth - margin)),
      y: Math.max(margin, Math.min(position.y, innerHeight - menu.offsetHeight - margin)) });
    menu.querySelector<HTMLButtonElement>('button:not(:disabled)')?.focus();
  }, [position]);
  useEffect(() => {
    const outside = (event: Event) => { if (!event.composedPath().includes(ref.current!)) onClose(); };
    window.addEventListener('pointerdown', outside, true);
    window.addEventListener('scroll', onClose, true);
    window.addEventListener('resize', onClose);
    return () => {
      window.removeEventListener('pointerdown', outside, true);
      window.removeEventListener('scroll', onClose, true);
      window.removeEventListener('resize', onClose);
    };
  }, [onClose]);
  const run = (action: (ids: string[]) => void) => { onClose(); action(position.ids); };
  return createPortal(<div ref={ref} className="clip-context-menu" role="menu" aria-label="片段操作"
    style={{ left: point.x, top: point.y }} onContextMenu={event => event.preventDefault()}
    onKeyDown={event => {
      if (event.key === 'Escape' || event.key === 'Tab') { event.stopPropagation(); onClose(); return; }
      if (!['ArrowDown', 'ArrowUp', 'Home', 'End'].includes(event.key)) return;
      event.preventDefault(); event.stopPropagation();
      const buttons = Array.from(ref.current!.querySelectorAll<HTMLButtonElement>('button:not(:disabled)'));
      const index = buttons.indexOf(document.activeElement as HTMLButtonElement);
      const next = event.key === 'Home' ? 0 : event.key === 'End' ? buttons.length - 1
        : (index + (event.key === 'ArrowUp' ? -1 : 1) + buttons.length) % buttons.length;
      buttons[next]?.focus();
    }}>
    <button type="button" role="menuitem" disabled={position.ids.length < 2} onClick={() => run(onMerge)}><Icon name="merge" />合并所选片段…</button>
    <button type="button" role="menuitem" className="danger" onClick={() => run(onDelete)}><Icon name="trash" />{position.ids.length > 1 ? `删除所选 ${position.ids.length} 个片段` : '删除片段'}</button>
  </div>, document.body);
}
