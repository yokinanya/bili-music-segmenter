'use client';
import { useRef, useState } from 'react';
import type { Clip, ClipEditProgress as EditProgress } from '@/lib/types';
import { api } from '@/lib/api';
import { errorText } from '@/lib/format';
import { Button, MaterialDialog, TextField } from './Material';
import { ClipEditProgress } from './ClipEditProgress';
import { titleCandidates } from '@/lib/titleCandidates';

interface Props { jobId: string; clip: Clip; onClose: () => void; onSaved: () => void }
export function ClipEditor({ jobId, clip, onClose, onSaved }: Props) {
  const [title, setTitle] = useState(clip.title), [artist, setArtist] = useState(clip.artist);
  const [start, setStart] = useState(String(clip.start_seconds)), [end, setEnd] = useState(String(clip.end_seconds));
  const [busy, setBusy] = useState(false), [error, setError] = useState('');
  const [progress, setProgress] = useState<EditProgress>({ stage: 'preparing', completed_seconds: 0, total_seconds: null, elapsed_seconds: 0 });
  const changesBounds = Number(start) !== clip.start_seconds || Number(end) !== clip.end_seconds;
  const candidates = titleCandidates(clip.recognition, clip.title_resolution);
  const pick = (value: string, artistValue: string) => { setTitle(value); setArtist(artistValue); };
  const form = useRef<HTMLFormElement>(null);
  const save = async () => {
    if (!form.current?.reportValidity() || busy) return;
    const start_seconds = Number(start), end_seconds = Number(end);
    if (end_seconds <= start_seconds) { setError('结束时间必须晚于开始时间'); return; }
    setBusy(true); setError('');
    setProgress({ stage: 'preparing', completed_seconds: 0, total_seconds: null, elapsed_seconds: 0 });
    try {
      await api.editClip(jobId, clip.id, { data: { title, artist, start_seconds, end_seconds }, update: setProgress });
      onSaved(); onClose();
    } catch (cause) { setError(errorText(cause)); }
    finally { setBusy(false); }
  };
  return <MaterialDialog open title="编辑片段" dismissible={!busy} onClose={() => { if (!busy) onClose(); }}>
    <form ref={form} className="clip-editor" onSubmit={(event) => { event.preventDefault(); void save(); }}>
      <p className="helper">时间是原视频里的秒数。只改歌名或歌手会直接保存；改了时间会重新导出片段。</p>
      {candidates.length > 0 && <div className="title-candidates"><p className="helper">
        {candidates.length > 1 ? '两个识曲结果不一样，请选一个或自己填：' : '识曲结果：'}</p>
        <div className="title-candidate-list">{candidates.map((item) =>
          <Button key={`${item.title}-${item.sources.join()}`} variant="text" disabled={busy}
            onClick={() => pick(item.title, item.artist)}>{item.title}
            {item.artist && <span className="muted"> · {item.artist}</span>}
            <span className="muted"> · {item.sources.join('/')}</span></Button>)}</div>
      </div>}
      <TextField label="歌曲标题" value={title} onChange={setTitle} disabled={busy} />
      <TextField label="歌手" value={artist} onChange={setArtist} disabled={busy} />
      <div className="field-grid">
        <label>开始时间 / 秒<input type="number" required min="0" step="0.001" value={start} disabled={busy} onChange={(event) => setStart(event.target.value)} /></label>
        <label>结束时间 / 秒<input type="number" required min="0" step="0.001" value={end} disabled={busy} onChange={(event) => setEnd(event.target.value)} /></label>
      </div>
      {busy && <ClipEditProgress progress={progress} />}
      {error && <div className="error" role="alert">{error}</div>}
      <div className="dialog-actions"><Button disabled={busy} onClick={onClose}>取消</Button><Button variant="filled" disabled={busy} onClick={() => void save()}>{busy ? '正在保存…' : changesBounds ? '保存并重新导出' : '保存修改'}</Button></div>
    </form>
  </MaterialDialog>;
}
