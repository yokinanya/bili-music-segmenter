import { useState } from 'react';
import { mediaTime } from '@/lib/format';
import { Field, IconButton } from './Material';
import { Icon } from './Icon';
import type { SongClip } from '@/lib/editor';
import { BoundaryNudge } from './BoundaryNudge';

interface Props {
  canUndo: boolean; canRedo: boolean; canSplit: boolean; hasSelection: boolean;
  duration: number; snapping: boolean; marks: { start: number | null; end: number | null };
  onUndo: () => void; onRedo: () => void; onAdd: () => void; onSplit: () => void;
  onMarkIn: () => void; onMarkOut: () => void; onClearMarks: () => void; onSnap: () => void;
  onFit: (selection: boolean) => void;
  clip: SongClip | undefined; onClipChange: (clip: SongClip) => void; onLocate: (time: number) => void;
}
export function TimelineToolbar(props: Props) {
  const [boundaryOpen, setBoundaryOpen] = useState(true);
  const [panel, setPanel] = useState<'edit' | 'boundary'>('edit');
  const valid = props.marks.start !== null && props.marks.end !== null && props.marks.start < props.marks.end;
  return <div className={`timeline-floating-tools ${boundaryOpen ? 'boundary-open' : ''}`} data-panel={panel}>
    <div className="timeline-panel-switch" role="group" aria-label="时间轴工具面板">
      <button type="button" aria-pressed={panel === 'edit'} onClick={() => setPanel('edit')}>编辑</button>
      <button type="button" aria-pressed={panel === 'boundary'} disabled={!props.clip} onClick={() => { setBoundaryOpen(true); setPanel('boundary'); }}>切点</button>
    </div>
    {props.clip && <section className="timeline-boundary-tools" aria-label="选中片段切点调整" inert={!boundaryOpen}>
      <div className="timeline-boundary-fields" key={props.clip.id}>
        <Field label="入点 / 秒" min="0" max={String(props.clip.end_seconds - .001)} step="0.001" value={props.clip.start_seconds}
          onChange={value => props.clip && props.onClipChange({ ...props.clip, start_seconds: value })} />
        <Field label="出点 / 秒" min={String(props.clip.start_seconds + .001)} max={String(props.duration)} step="0.001" value={props.clip.end_seconds}
          onChange={value => props.clip && props.onClipChange({ ...props.clip, end_seconds: value })} />
      </div>
      <BoundaryNudge key={props.clip.id} clip={props.clip} duration={props.duration} onChange={props.onClipChange} onLocate={props.onLocate} />
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
    </div>
    {(props.marks.start !== null || props.marks.end !== null) && <span className={`timeline-mark-summary ${valid ? '' : 'invalid'}`} role="status">
      {props.marks.start === null ? '未设入点' : mediaTime(props.marks.start)} — {props.marks.end === null ? '未设出点' : mediaTime(props.marks.end)}
      {!valid && props.marks.start !== null && props.marks.end !== null && ' · 出点须晚于入点'}
    </span>}
  </div></div>;
}
