'use client';
import type { SongClip } from '@/lib/editor';
import { titleCandidates } from '@/lib/titleCandidates';
import { mediaTime as clock } from '@/lib/format';
import { updateSongTitle } from '@/lib/editor';
import { SongSearchDialog } from './SongSearchDialog';
import { Button, TextField } from './Material';

interface Props { clip: SongClip | undefined; onChange: (clip: SongClip) => void }

export function SongProperties({ clip, onChange }: Props) {
  if (!clip) return <aside className="song-properties" aria-label="片段属性"><header><h2>片段属性</h2></header>
    <div className="property-scroll"><div className="properties-empty"><span aria-hidden="true">◇</span><strong>尚未选择片段</strong><p>选择一个歌曲区间以编辑信息。</p></div></div></aside>;
  const candidates = titleCandidates(clip.recognition, clip.title_resolution);
  return <aside className="song-properties" aria-label="片段属性"><header><h2>片段属性</h2><span className="property-length">{clock(clip.end_seconds - clip.start_seconds)}</span></header>
    <div className="property-scroll property-editor">
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
