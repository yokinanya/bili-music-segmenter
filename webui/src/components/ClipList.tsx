'use client';
import { useState } from 'react';
import { downloadUrl } from '@/lib/api';
import { isActive, type Clip, type JobStatus } from '@/lib/types';
import { Icon } from './Icon';
import { ActionLink, Button } from './Material';
import { ClipEditor } from './ClipEditor';
import { ClipRow } from './ClipRow';
import { Disclosure } from './Disclosure';
import { ManifestView } from './ManifestView';
import './clip-list.css';
export function ClipList({ job, mediaId, onChanged }: { job: JobStatus; mediaId: string; onChanged?: () => void }) {
  const clips = job.clips.filter((clip) => clip.media_id === mediaId);
  const [editing, setEditing] = useState<Clip | null>(null);
  const [manifest, setManifest] = useState(false);
  return <div className="results"><div className="section-head"><h3>片段 <span className="counter">{clips.length}</span></h3>
    {!isActive(job.state) && <ActionLink href={downloadUrl(job.id, 'archive')}><Icon name="download" />整批 ZIP</ActionLink>}</div>
    {clips.length === 0 && <div className="empty pane-empty"><Icon name="music" /><span>{isActive(job.state) ? '等待导出片段' : '暂无片段'}</span></div>}
    {clips.length > 0 && <ol className="clip-list" aria-label="歌曲列表">{clips.map(clip =>
      <li key={clip.id}><ClipRow jobId={job.id} clip={clip} canEdit={!isActive(job.state)} onEdit={setEditing} /></li>)}</ol>}
    <Disclosure title="分析详情" className="clip-analysis">
      <div className="clip-actions"><Button onClick={() => setManifest(true)}>查看分析 JSON</Button>
        <ActionLink href={downloadUrl(job.id, `manifest/${mediaId}`, true)} download>下载 JSON</ActionLink></div>
    </Disclosure>
    {editing && <ClipEditor key={editing.id} jobId={job.id} clip={editing} onClose={() => setEditing(null)} onSaved={() => onChanged?.()} />}
    {manifest && <ManifestView jobId={job.id} mediaId={mediaId} onClose={() => setManifest(false)} />}
  </div>;
}
