'use client';
import { useState } from 'react';
import { clipUrl, downloadUrl } from '@/lib/api';
import { isActive, type Clip, type JobStatus } from '@/lib/types';
import { Icon } from './Icon';
import { ActionLink, Button } from './Material';
import { ClipEditor } from './ClipEditor';
import { Disclosure } from './Disclosure';
import { ManifestView } from './ManifestView';
import { MediaPlayer } from './MediaPlayer';
export function ClipList({ job, mediaId, onChanged }: { job: JobStatus; mediaId: string; onChanged?: () => void }) {
  const clips = job.clips.filter((clip) => clip.media_id === mediaId);
  const [editing, setEditing] = useState<Clip | null>(null);
  const [manifest, setManifest] = useState(false);
  return <div className="results"><div className="section-head"><h3>片段 <span className="counter">{clips.length}</span></h3>
    {!isActive(job.state) && <ActionLink href={downloadUrl(job.id, 'archive')}><Icon name="download" />整批 ZIP</ActionLink>}</div>
    <div className="clip-actions"><Button onClick={() => setManifest(true)}>查看分析 JSON</Button><ActionLink href={downloadUrl(job.id, `manifest/${mediaId}`, true)} download>下载 JSON</ActionLink></div>
    {clips.length === 0 && <div className="empty pane-empty"><Icon name="music" /><span>{isActive(job.state) ? '等待导出片段' : '暂无片段'}</span></div>}
    {clips.map((clip) => <article className="clip" key={clip.id}><MediaPlayer key={`${clip.id}:${clip.name}:${clip.start_seconds}:${clip.end_seconds}`} src={`${clipUrl(job.id, clip.id)}&revision=${encodeURIComponent(`${clip.name}:${clip.start_seconds}:${clip.end_seconds}`)}`} label={clip.title || clip.name} />
      <div className="section-head clip-heading"><div><h3>{clip.title || '未识别歌名'}</h3><p className="muted">{clip.artist || '未知歌手'} · {Math.round(clip.duration_seconds)} 秒</p></div><ActionLink href={clipUrl(job.id, clip.id, true)} download={clip.name} aria-label={`下载 ${clip.title || clip.name}`}><Icon name="download" />下载</ActionLink></div>
      <p className="clip-metadata">原视频 {clip.start_seconds}–{clip.end_seconds} 秒 · {clip.source_name}</p>
      <p className="helper">文件：{clip.name}</p>
      {(clip.recognition != null || clip.title_resolution != null) && <Disclosure title="识别与复核依据"><pre className="clip-evidence">{JSON.stringify({ recognition: clip.recognition, title_resolution: clip.title_resolution }, null, 2)}</pre></Disclosure>}
      {!isActive(job.state) && <Button variant="outlined" onClick={() => setEditing(clip)}>编辑标题与边界</Button>}
    </article>)}
    {editing && <ClipEditor key={editing.id} jobId={job.id} clip={editing} onClose={() => setEditing(null)} onSaved={() => onChanged?.()} />}
    {manifest && <ManifestView jobId={job.id} mediaId={mediaId} onClose={() => setManifest(false)} />}
  </div>;
}
