'use client';
import { useId, useState } from 'react';
import type { Clip } from '@/lib/types';
import { clipUrl } from '@/lib/api';
import { mediaTime } from '@/lib/format';
import { ActionLink, Button } from './Material';
import { Icon } from './Icon';
import { ClipEvidence } from './ClipEvidence';
import { MediaPlayer } from './MediaPlayer';

interface ClipRowProps {
  readonly jobId: string;
  readonly clip: Clip;
  readonly canEdit: boolean;
  readonly onEdit: (clip: Clip) => void;
}

function ClipDetails({ jobId, clip, canEdit, onEdit }: ClipRowProps) {
  const revision = `${clip.name}:${clip.start_seconds}:${clip.end_seconds}`;
  return <>
    <MediaPlayer key={revision} src={`${clipUrl(jobId, clip.id)}&revision=${encodeURIComponent(revision)}`}
      label={clip.title || clip.name} />
    <p className="clip-metadata">来源 {clip.source_name}</p>
    <p className="clip-metadata">文件 {clip.name}</p>
    {canEdit && <div className="clip-actions">
      <Button variant="outlined" onClick={() => onEdit(clip)}>编辑标题与边界</Button>
    </div>}
    {(clip.recognition != null || clip.title_resolution != null) && <ClipEvidence clip={clip} />}
  </>;
}

export function ClipRow(props: ClipRowProps) {
  const { jobId, clip } = props;
  const [open, setOpen] = useState(false);
  const detailsId = useId();
  const title = clip.title || '未识别歌名';
  return <article className={`clip ${open ? 'clip-open' : ''}`}>
    <div className="clip-row">
      <Button variant="text" className="clip-toggle" aria-expanded={open} aria-controls={detailsId}
        aria-label={`${open ? '收起' : '展开'} ${title}`} onClick={() => setOpen(value => !value)}>
        <span className="clip-summary">
          <span className="clip-title">{title}</span>
          <span className="clip-subtitle">{clip.artist || '未知歌手'} · {mediaTime(clip.duration_seconds)}</span>
          <span className="clip-range">原视频 {mediaTime(clip.start_seconds)}–{mediaTime(clip.end_seconds)}</span>
        </span>
        <Icon name={open ? 'up' : 'down'} />
      </Button>
      <ActionLink className="clip-download" href={clipUrl(jobId, clip.id, true)} download={clip.name}
        aria-label={`下载 ${clip.title || clip.name}`}><Icon name="download" />下载</ActionLink>
    </div>
    <div id={detailsId} className="clip-details" hidden={!open}>{open && <ClipDetails {...props} />}</div>
  </article>;
}
