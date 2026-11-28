import { useState } from 'react';
import { mediaTime } from '@/lib/format';
import { ZOOM_STEPS } from '@/lib/timelineZoom';
import { IconButton, Slider } from './Material';
import { Icon } from './Icon';
import type { SongClip } from '@/lib/editor';
import { BoundaryNudge } from './BoundaryNudge';

interface Props {
  canUndo: boolean; canRedo: boolean; canSplit: boolean; hasSelection: boolean;
  duration: number; snapping: boolean; marks: { start: number | null; end: number | null };
  onUndo: () => void; onRedo: () => void; onAdd: () => void; onSplit: () => void;
  onMarkIn: () => void; onMarkOut: () => void; onClearMarks: () => void; onSnap: () => void;
  onFit: (selection: boolean) => void; zoom: number; onZoomChange: (zoom: number) => void;
  clip: SongClip | undefined; onClipChange: (clip: SongClip) => void; onLocate: (time: number) => void;
}
export function TimelineToolbar(props: Props) {
  const [boundaryOpen, setBoundaryOpen] = useState(true);
  const [panel, setPanel] = useState<'edit' | 'boundary'>('edit');
  const { clip } = props;
  const activePanel = clip ? panel : 'edit';
  const valid = props.marks.start !== null && props.marks.end !== null && props.marks.start < props.marks.end;
  return <header className="timeline-topbar" data-panel={activePanel}>
    <div className="timeline-panel-switch" role="group" aria-label="时间轴工具面板">
      <button type="button" aria-pressed={activePanel === 'edit'} onClick={() => setPanel('edit')}>编辑</button>
      <button type="button" aria-pressed={activePanel === 'boundary'} disabled={!clip} onClick={() => { setBoundaryOpen(true); setPanel('boundary'); }}>切点</button>
    </div>
    {clip && <section key={clip.id} className="timeline-boundary-tools" aria-label="选中片段切点调整" hidden={!boundaryOpen}>
      <BoundaryNudge clip={clip} duration={props.duration} onChange={props.onClipChange} onLocate={props.onLocate} />
    </section>}
    <div className="timeline-toolbar" role="toolbar" aria-label="时间轴编辑工具">
    <IconButton className="timeline-boundary-toggle" aria-pressed={boundaryOpen} aria-expanded={boundaryOpen} disabled={!props.clip}
      onClick={() => setBoundaryOpen(value => !value)} label={boundaryOpen ? '收起切点调整' : '展开切点调整'}><Icon name="edit" /></IconButton>
    <div className="timeline-group">
      <IconButton onClick={props.onUndo} disabled={!props.canUndo} label="撤销"><Icon name="undo" /></IconButton>
      <IconButton onClick={props.onRedo} disabled={!props.canRedo} label="重做"><Icon name="redo" /></IconButton>
    </div><span className="timeline-divider" />
    <div className="timeline-group">
      <IconButton onClick={props.onMarkIn} disabled={!props.duration} label="标记区间入点（[）" aria-pressed={props.marks.start !== null}><Icon name="mark-in" /></IconButton>
      <IconButton onClick={props.onMarkOut} disabled={!props.duration} label="标记区间出点（]）" aria-pressed={props.marks.end !== null}><Icon name="mark-out" /></IconButton>
      <IconButton onClick={props.onAdd} disabled={!valid} label="从标记创建区间（Enter）"><Icon name="plus" /></IconButton>
      <IconButton onClick={props.onClearMarks} disabled={props.marks.start === null && props.marks.end === null} label="清除入出点标记"><Icon name="close" /></IconButton>
    </div><span className="timeline-divider" />
    <div className="timeline-group">
      <IconButton onClick={props.onSplit} disabled={!props.canSplit} label="在此处分割（S）"><Icon name="scissors" /></IconButton>
      <IconButton aria-pressed={props.snapping} onClick={props.onSnap} label={`吸附播放头及片段边界：${props.snapping ? '开启' : '关闭'}（Shift 临时关闭）`}><Icon name="magnet" /></IconButton>
    </div><span className="timeline-divider" />
    <div className="timeline-zoom">
      <IconButton onClick={() => props.onFit(false)} label="缩放至全部"><Icon name="fullscreen" /></IconButton>
      <IconButton onClick={() => props.onFit(true)} disabled={!props.hasSelection} label="缩放至选中片段"><Icon name="target" /></IconButton>
      <span>缩放</span>
      <Slider label="时间轴缩放" max={ZOOM_STEPS.length - 1} value={ZOOM_STEPS.indexOf(props.zoom)} onChange={value => props.onZoomChange(ZOOM_STEPS[value])} />
      <span className="timeline-zoom-value">{props.zoom}×</span>
    </div>
    {(props.marks.start !== null || props.marks.end !== null) && <span className={`timeline-mark-summary ${valid ? '' : 'invalid'}`} role="status">
      {props.marks.start === null ? '未设入点' : mediaTime(props.marks.start)} — {props.marks.end === null ? '未设出点' : mediaTime(props.marks.end)}
      {!valid && props.marks.start !== null && props.marks.end !== null && ' · 出点须晚于入点'}
    </span>}
  </div></header>;
}
