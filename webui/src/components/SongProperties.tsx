'use client';
import type { SongClip } from '@/lib/editor';
import { titleCandidates } from '@/lib/titleCandidates';
import { mediaTime as clock } from '@/lib/format';
import { updateSongTitle } from '@/lib/editor';
import { SongSearchDialog } from './SongSearchDialog';
import { Button, Field, TextField } from './Material';
import { BoundaryNudge } from './BoundaryNudge';

interface Props { clip: SongClip | undefined; duration: number; onChange: (clip: SongClip) => void; onLocate: (time: number) => void }

export function SongProperties({ clip, duration, onChange, onLocate }: Props) {
  if (!clip) return <aside className="song-properties" aria-label="片段属性"><header><h2>片段属性</h2></header>
    <div className="property-scroll"><div className="properties-empty"><span aria-hidden="true">◇</span><strong>尚未选择片段</strong><p>选择一个歌曲区间以编辑信息。</p></div></div></aside>;
  const candidates = titleCandidates(clip.recognition, clip.title_resolution);
  return <aside className="song-properties" aria-label="片段属性"><header><h2>片段属性</h2><span className="property-length">{clock(clip.end_seconds - clip.start_seconds)}</span></header>
    <div className="property-scroll property-editor">
      <section><h3>切点</h3><div className="property-grid">
        <Field label="入点 / 秒" min="0" max={String(clip.end_seconds - .001)} step="0.001" value={clip.start_seconds} onChange={value => onChange({ ...clip, start_seconds: value })} />
        <Field label="出点 / 秒" min={String(clip.start_seconds + .001)} max={String(duration)} step="0.001" value={clip.end_seconds} onChange={value => onChange({ ...clip, end_seconds: value })} />
      </div><BoundaryNudge key={clip.id} clip={clip} duration={duration} onChange={onChange} onLocate={onLocate} /></section>
      <section><div className="property-section-heading"><h3>歌曲信息</h3>
        <SongSearchDialog key={clip.id} initialQuery={clip.title} onChoose={song => onChange(updateSongTitle(clip, song.title))} />
      </div>
        <TextField label="歌曲名" value={clip.title} onChange={value => onChange(updateSongTitle(clip, value))} />
        <TextField label="导出文件名" value={clip.name} onChange={value => onChange({ ...clip, name: value })} />
      </section>
      {candidates.length > 0 && <section><h3>识曲候选</h3><div className="property-candidates">{candidates.map(candidate => <Button variant="outlined" key={candidate.title} onClick={() => onChange(updateSongTitle(clip, candidate.title))}>
        {candidate.title} · {candidate.sources.join(' / ')}</Button>)}</div></section>}
    </div></aside>;
}
