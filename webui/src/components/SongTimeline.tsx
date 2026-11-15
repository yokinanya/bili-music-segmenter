'use client';
import { useEffect, useLayoutEffect, useRef, useState } from 'react';
import type { SongClip } from '@/lib/editor';
import { timeAt } from '@/lib/editor';
import type { Waveform } from '@/lib/editorApi';
import { mediaTime as clock } from '@/lib/format';
import { usePointerSeek } from '@/lib/usePointerSeek';
import { bindTimelineZoom, ZOOM_STEPS } from '@/lib/timelineZoom';
import { timelineTickTranslation, timelineWidth } from '@/lib/timelineLayout';
import { IconButton, Slider } from './Material';
import { Icon } from './Icon';

interface Props {
  duration: number; time: number; clips: SongClip[]; selected: string[]; waveform: Waveform | null;
  canUndo: boolean; canRedo: boolean;
  onSeek: (time: number) => void; onSelect: (id: string, multi: boolean) => void; onChange: (clips: SongClip[]) => void;
  onAdd: () => void; onSplit: () => void; onDelete: () => void; onUndo: () => void; onRedo: () => void;
}
export function SongTimeline(props: Props) {
  const [zoom, setZoom] = useState(1), [scroll, setScroll] = useState(0);
  const jumping = (edge: 'start' | 'end') => {
    const clip = props.clips.find(item => props.selected.includes(item.id)) ?? props.clips[0];
    if (clip) props.onSeek(edge === 'start' ? clip.start_seconds : clip.end_seconds);
  };
  const viewport = useRef<HTMLDivElement>(null), canvas = useRef<HTMLCanvasElement>(null);
  const [width, setWidth] = useState(800);
  const pendingScroll = useRef<number | null>(null);
  useLayoutEffect(() => {
    const element = viewport.current;
    if (!element) return;
    if (pendingScroll.current !== null) element.scrollLeft = pendingScroll.current;
    pendingScroll.current = null;
    return bindTimelineZoom({ element, zoom, onZoom: position => {
      pendingScroll.current = position.scrollLeft;
      setZoom(position.zoom);
    } });
  }, [zoom]);
  const scale = width / Math.max(1, props.duration) * zoom;
  const stepZoom = (direction: number) => {
    const index = ZOOM_STEPS.indexOf(zoom);
    const next = ZOOM_STEPS[Math.max(0, Math.min(ZOOM_STEPS.length - 1, index + direction))];
    setZoom(next);
    requestAnimationFrame(() => {
      const nextScale = width / Math.max(1, props.duration) * next;
      if (viewport.current) viewport.current.scrollLeft = Math.max(0, props.time * nextScale - width / 2);
    });
  };
  useEffect(() => {
    const observer = new ResizeObserver(entries => setWidth(entries[0].contentRect.width));
    if (viewport.current) observer.observe(viewport.current);
    return () => observer.disconnect();
  }, []);
  useEffect(() => {
    const node = canvas.current;
    if (!node) return;
    node.width = width; node.height = 56;
    const context = node.getContext('2d');
    if (!context) return;
    context.clearRect(0, 0, width, 56);
    if (!props.waveform) return;
    context.fillStyle = 'currentColor';
    context.globalAlpha = .55;
    for (let x = 0; x < width; x += 2) {
      const start = Math.floor((scroll + x) / scale / props.waveform.seconds_per_peak);
      const end = Math.ceil((scroll + x + 2) / scale / props.waveform.seconds_per_peak);
      let peak = 0;
      for (let i = start; i < end; i++) peak = Math.max(peak, props.waveform.peaks[i] ?? 0);
      context.fillRect(x, 28 - peak * 26, 1, Math.max(1, peak * 52));
    }
  }, [props.waveform, width, scale, scroll]);
  const position = (x: number) => timeAt({ x, left: viewport.current!.getBoundingClientRect().left, scroll: viewport.current!.scrollLeft, pixelsPerSecond: scale, duration: props.duration });
  const seekPointer = usePointerSeek({ enabled: props.duration > 0, onSeek: x => props.onSeek(position(x)) });
  const drag = (event: React.PointerEvent<HTMLButtonElement>, clip: SongClip, edge: 'start_seconds' | 'end_seconds') => {
    event.stopPropagation(); event.currentTarget.setPointerCapture(event.pointerId);
    const button = event.currentTarget;
    const finish = (up: PointerEvent) => {
      button.removeEventListener('pointerup', finish);
      const value = Math.round(position(up.clientX) * 1000) / 1000;
      if (edge === 'start_seconds' ? value >= clip.end_seconds : value <= clip.start_seconds) return;
      props.onChange(props.clips.map(item => item.id === clip.id ? { ...item, [edge]: value } : item));
    };
    button.addEventListener('pointerup', finish, { once: true });
  };
  return <section className="song-timeline" aria-label="原视频时间轴">
    <div className="timeline-toolbar">
      <span className="timeline-title">时间轴</span>
      <div className="timeline-group">
        <IconButton onClick={props.onUndo} disabled={!props.canUndo} label="撤销"><Icon name="undo" /></IconButton>
        <IconButton onClick={props.onRedo} disabled={!props.canRedo} label="重做"><Icon name="redo" /></IconButton>
      </div>
      <div className="timeline-group">
        <IconButton onClick={props.onAdd} disabled={!props.duration} label="添加区间"><Icon name="plus" /></IconButton>
        <IconButton onClick={props.onSplit} disabled={!props.selected.length} label="在播放头拆分"><Icon name="split" /></IconButton>
        <IconButton onClick={props.onDelete} disabled={!props.selected.length} label="删除选中"><Icon name="trash" /></IconButton>
      </div>
      <span className="timeline-meta">Ctrl / ⌘ 多选 · Ctrl / ⌘ + 滚轮缩放 · 空格播放</span>
      <div className="timeline-zoom">缩放 <Slider label="时间轴缩放" max={ZOOM_STEPS.length - 1} value={ZOOM_STEPS.indexOf(zoom)} onChange={value => setZoom(ZOOM_STEPS[value])} />
      <IconButton onClick={() => stepZoom(-1)} disabled={zoom === ZOOM_STEPS[0]} label="缩小时间轴"><Icon name="minus" /></IconButton>
      <IconButton onClick={() => stepZoom(1)} disabled={zoom === ZOOM_STEPS.at(-1)} label="放大时间轴"><Icon name="plus" /></IconButton>
    </div>
    </div>
    <div className="timeline-viewport" ref={viewport} tabIndex={0} aria-label="时间轴键盘操作：左右方向键跳到选中区间的入点或出点"
      onScroll={e => setScroll(e.currentTarget.scrollLeft)} onKeyDown={e => {
        if (e.key === 'ArrowLeft') { e.preventDefault(); jumping('start'); }
        if (e.key === 'ArrowRight') { e.preventDefault(); jumping('end'); }
      }}>
      <div className="timeline-content" style={{ width: timelineWidth(width, zoom), height: 176 }} {...seekPointer}>
        <div className="time-ruler">{Array.from({ length: 11 }, (_, index) => <span key={index} style={{ left: `${index * 10}%`, transform: `translateX(${timelineTickTranslation(index, 11)})` }}>{clock(props.duration * index / 10)}</span>)}</div>
        <div className="timeline-wave"><canvas ref={canvas} className="waveform-canvas" aria-label="源视频音频波形" />{!props.waveform && <span>波形准备中…</span>}</div>
        <div className="song-track">{props.clips.map((clip, index) => <div key={clip.id} className={`song-region ${props.selected.includes(clip.id) ? 'selected' : ''}`}
          style={{ left: clip.start_seconds * scale, width: Math.max(3, (clip.end_seconds - clip.start_seconds) * scale) }}
          onPointerDown={event => event.stopPropagation()} onClick={e => { e.stopPropagation(); props.onSelect(clip.id, e.ctrlKey || e.metaKey); }}>
          <button className="song-handle" aria-label={`${clip.title || '片段'} 入点`} onPointerDown={e => drag(e, clip, 'start_seconds')} onClick={e => e.stopPropagation()} />
          <span><small>{String(index + 1).padStart(2, '0')}</small>{clip.title || '待命名歌曲'}</span>
          <button className="song-handle end" aria-label={`${clip.title || '片段'} 出点`} onPointerDown={e => drag(e, clip, 'end_seconds')} onClick={e => e.stopPropagation()} />
        </div>)}</div>
        <div className="timeline-playhead" style={{ left: props.time * scale }}><i /></div>
      </div>
    </div>
  </section>;
}
