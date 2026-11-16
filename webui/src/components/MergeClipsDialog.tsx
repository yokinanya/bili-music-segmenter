import type { SongClip } from '@/lib/editor';
import { mediaTime } from '@/lib/format';
import { Button, MaterialDialog } from './Material';

interface Props { clips: SongClip[] | null; onClose: () => void; onConfirm: () => void }
export function MergeClipsDialog({ clips, onClose, onConfirm }: Props) {
  const ordered = [...(clips ?? [])].sort((a, b) => a.start_seconds - b.start_seconds);
  let end = ordered[0]?.end_seconds ?? 0;
  const gaps = ordered.flatMap(clip => {
    const gap = clip.start_seconds > end ? [{ start: end, end: clip.start_seconds }] : [];
    end = Math.max(end, clip.end_seconds);
    return gap;
  });
  return <MaterialDialog open={clips !== null} title="合并选中片段" onClose={onClose}>
    <p>将以下 {ordered.length} 个片段合并为一个连续区间，保留第一个片段的歌曲信息。操作可撤销。</p>
    <ul className="merge-clip-list">{ordered.map(clip => <li key={clip.id}>
      <strong>{clip.title || clip.name}</strong><span>{mediaTime(clip.start_seconds)} — {mediaTime(clip.end_seconds)}</span>
    </li>)}</ul>
    {ordered.length > 0 && <p>合并范围：{mediaTime(ordered[0].start_seconds)} — {mediaTime(end)}</p>}
    {gaps.length > 0 ? <><p className="merge-gap-warning">以下间隔也会保留在合并结果中，不会自动剪除：</p>
      <ul>{gaps.map(gap => <li key={gap.start}>{mediaTime(gap.start)} — {mediaTime(gap.end)}（{(gap.end - gap.start).toFixed(2)} 秒）</li>)}</ul>
    </> : <p>片段连续或重叠，不会包含额外间隔。</p>}
    <div className="dialog-actions"><Button variant="text" onClick={onClose}>取消</Button>
      <Button variant="filled" disabled={ordered.length < 2} onClick={onConfirm}>{gaps.length ? '确认合并并保留间隔' : '确认合并'}</Button></div>
  </MaterialDialog>;
}
