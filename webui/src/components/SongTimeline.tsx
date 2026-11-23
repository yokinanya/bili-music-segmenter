'use client';
import { useEffect, useLayoutEffect, useRef, useState } from 'react';
import type { SongClip } from '@/lib/editor';
import { timeAt } from '@/lib/editor';
import type { Waveform } from '@/lib/editorApi';
import { mediaTime as clock } from '@/lib/format';
import { usePointerSeek } from '@/lib/usePointerSeek';
import { useTimelineTrim } from '@/lib/useTimelineTrim';
import { bindTimelineZoom, ZOOM_STEPS } from '@/lib/timelineZoom';
import { revealTimelinePosition, timelineTickTranslation, timelineWidth } from '@/lib/timelineLayout';
import { TimelineToolbar } from './TimelineToolbar';
import { Button, Slider } from './Material';
import { ClipContextMenu, type ClipMenuPosition } from './ClipContextMenu';

interface Props {
  duration: number; time: number; clips: SongClip[]; selected: string[]; waveform: Waveform | null;
  listJump: { time: number } | null;
  canUndo: boolean; canRedo: boolean;
  canSplit: boolean; marks: { start: number | null; end: number | null };
  onMarkIn: () => void; onMarkOut: () => void; onClearMarks: () => void;
  onLocate: (time: number) => void;
  onMerge: (ids: string[]) => void; onSave: () => void; saving: boolean;
  onSeek: (time: number) => void; onSelect: (id: string, multi: boolean) => void; onChange: (clips: SongClip[]) => void;
  onAdd: () => void; onSplit: () => void; onDelete: (ids: string[]) => void; onUndo: () => void; onRedo: () => void;
}
export function SongTimeline(props: Props) {
  const [zoom, setZoom] = useState(1), [scroll, setScroll] = useState(0);
  const [snapping, setSnapping] = useState(true);
  const [menu, setMenu] = useState<ClipMenuPosition | null>(null);
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
  const lastListJump = useRef<Props['listJump']>(null);
  useLayoutEffect(() => {
    const element = viewport.current;
    const jump = props.listJump;
    if (!element || !jump || jump === lastListJump.current) return;
    lastListJump.current = jump;
    element.scrollLeft = revealTimelinePosition(jump.time * scale, {
      width: element.clientWidth, scrollLeft: element.scrollLeft, scrollWidth: element.scrollWidth,
    });
  }, [props.listJump, scale]);
  const changeZoom = (next: number) => {
    setZoom(next);
    requestAnimationFrame(() => {
      const nextScale = width / Math.max(1, props.duration) * next;
      if (viewport.current) viewport.current.scrollLeft = Math.max(0, props.time * nextScale - width / 2);
    });
  };
  const fit = (selection: boolean) => {
    const clips = props.clips.filter(clip => props.selected.includes(clip.id));
    if (selection && !clips.length) return;
    const start = selection ? Math.min(...clips.map(clip => clip.start_seconds)) : 0;
    const end = selection ? Math.max(...clips.map(clip => clip.end_seconds)) : props.duration;
    const paddingRatio = 0.85;
    const desired = props.duration / Math.max(end - start, Number.EPSILON) * paddingRatio;
    const next = selection ? [...ZOOM_STEPS].reverse().find(value => value <= desired) ?? 1 : 1;
    pendingScroll.current = Math.max(0, (start + end) / 2 * width / Math.max(1, props.duration) * next - width / 2);
    if (next === zoom && viewport.current) { viewport.current.scrollLeft = pendingScroll.current; pendingScroll.current = null; }
    setZoom(next);
  };
  useEffect(() => {
    const observer = new ResizeObserver(entries => setWidth(entries[0].contentRect.width));
    if (viewport.current) observer.observe(viewport.current);
    return () => observer.disconnect();
  }, []);
  useEffect(() => {
    const node = canvas.current;
    if (!node) return;
    const pixelRatio = window.devicePixelRatio || 1;
    const waveHeight = 56;
    node.width = Math.round(width * pixelRatio); node.height = Math.round(waveHeight * pixelRatio);
    const context = node.getContext('2d');
    if (!context) return;
    context.scale(pixelRatio, pixelRatio);
    context.clearRect(0, 0, width, waveHeight);
    if (!props.waveform) return;
    context.fillStyle = getComputedStyle(node).color;
    context.globalAlpha = .8;
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
  const trim = useTimelineTrim({ clips: props.clips, duration: props.duration, time: props.time, scale,
    snapping, position, viewport, onChange: props.onChange });
  const boundary = trim.preview?.clip[trim.preview.edge];
  const selectedClip = props.clips.find(clip => clip.id === props.selected[0]);
  return <><section className="song-timeline" aria-label="原视频时间轴">
    <TimelineToolbar {...props} hasSelection={props.selected.length > 0} snapping={snapping}
      clip={selectedClip} onClipChange={value => props.onChange(props.clips.map(clip => clip.id === value.id ? value : clip))}
      onSnap={() => setSnapping(value => !value)} onFit={fit} />
    <div className="timeline-viewport" ref={viewport} tabIndex={0} aria-label="时间轴键盘操作：左右方向键跳到选中区间的入点或出点"
      onScroll={e => setScroll(e.currentTarget.scrollLeft)} onKeyDown={e => {
        if (e.key === 'ArrowLeft') { e.preventDefault(); jumping('start'); }
        if (e.key === 'ArrowRight') { e.preventDefault(); jumping('end'); }
      }}>
      <div className="timeline-content" style={{ width: timelineWidth(width, zoom), height: 176 }} {...seekPointer}>
        <div className="time-ruler">{Array.from({ length: 11 }, (_, index) => <span key={index} style={{ left: `${index * 10}%`, transform: `translateX(${timelineTickTranslation(index, 11)})` }}>{clock(props.duration * index / 10)}</span>)}</div>
        {props.marks.start !== null && props.marks.end !== null && props.marks.start < props.marks.end && <div className="timeline-mark-range"
          style={{ left: props.marks.start * scale, width: (props.marks.end - props.marks.start) * scale }} />}
        {props.marks.start !== null && <div className="timeline-mark start" style={{ left: props.marks.start * scale }}><b>入</b></div>}
        {props.marks.end !== null && <div className="timeline-mark end" style={{ left: props.marks.end * scale }}><b>出</b></div>}
        <div className="timeline-wave"><canvas ref={canvas} className="waveform-canvas" style={{ left: scroll, width }} aria-label="源视频音频波形" />{!props.waveform && <span>波形准备中…</span>}</div>
        <div className="song-track">{trim.clips.map((clip, index) => <div key={clip.id} className={`song-region ${props.selected.includes(clip.id) ? 'selected' : ''} ${trim.preview?.clip.id === clip.id ? 'trimming' : ''}`}
          style={{ left: clip.start_seconds * scale, width: Math.max(3, (clip.end_seconds - clip.start_seconds) * scale) }}
          onContextMenu={event => {
            event.preventDefault(); event.stopPropagation();
            const ids = props.selected.includes(clip.id) ? props.selected : [clip.id];
            if (!props.selected.includes(clip.id)) props.onSelect(clip.id, false);
            setMenu({ x: event.clientX, y: event.clientY, ids });
          }}
          onPointerDown={event => event.stopPropagation()} onClick={e => { e.stopPropagation(); props.onSelect(clip.id, e.ctrlKey || e.metaKey); }}>
          <button className="song-handle" aria-label={`${clip.title || '片段'} 入点`} {...trim.bind(clip, 'start_seconds')} onClick={e => e.stopPropagation()} />
          <span><small>{String(index + 1).padStart(2, '0')}</small>{clip.title || '待命名歌曲'}</span>
          <button className="song-handle end" aria-label={`${clip.title || '片段'} 出点`} {...trim.bind(clip, 'end_seconds')} onClick={e => e.stopPropagation()} />
        </div>)}</div>
        <div className={`timeline-playhead ${trim.preview?.snapTime === props.time ? 'snapped' : ''}`} style={{ left: props.time * scale }}><i /></div>
        {trim.preview?.snapTime != null && <div className="timeline-snap-guide" style={{ left: trim.preview.snapTime * scale }} />}
        {trim.preview && boundary !== undefined && <div className={`timeline-trim-label ${trim.preview.edge === 'start_seconds' ? 'start' : 'end'}`}
          style={{ left: Math.max(scroll, Math.min(scroll + width - 160, boundary * scale)) }}>
          {trim.preview.edge === 'start_seconds' ? '入点' : '出点'} {clock(boundary)}.{String(Math.round(boundary * 1000) % 1000).padStart(3, '0')}
          {trim.preview.snapTime !== null && ' · 已吸附'}
        </div>}
      </div>
    </div>
  </section><footer className="editor-status timeline-bottom-bar">
    <div className="timeline-bottom-zoom"><span>缩放</span>
      <Slider label="时间轴缩放" max={ZOOM_STEPS.length - 1} value={ZOOM_STEPS.indexOf(zoom)} onChange={value => changeZoom(ZOOM_STEPS[value])} />
      <span className="timeline-zoom-value">{zoom}×</span>
    </div>
    <Button variant="text" disabled={props.saving} onClick={props.onSave}>{props.saving ? '正在保存…' : '保存草稿'}</Button>
  </footer>{menu && <ClipContextMenu position={menu} onClose={() => setMenu(null)} onDelete={props.onDelete} onMerge={props.onMerge} />}</>;
}
