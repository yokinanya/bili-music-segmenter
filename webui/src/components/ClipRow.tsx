'use client';
import { useId, useState } from 'react';
import type { Clip } from '@/lib/types';
import { clipUrl } from '@/lib/api';
import { mediaTime } from '@/lib/format';
import { ActionLink, Button, IconButton } from './Material';
import { Icon } from './Icon';
import { ClipEvidence } from './ClipEvidence';
import { MediaPlayer } from './MediaPlayer';

interface ClipRowProps {
  readonly jobId: string;
  readonly clip: Clip;
  readonly canEdit: boolean;
  readonly onEdit: (clip: Clip) => void;
}

function ClipDetails({ jobId, clip }: ClipRowProps) {
  const revision = `${clip.name}:${clip.start_seconds}:${clip.end_seconds}`;
  return <>
    <MediaPlayer key={revision} src={`${clipUrl(jobId, clip.id)}&revision=${encodeURIComponent(revision)}`}
      label={clip.title || clip.name} />
    <dl className="clip-files">
      <dt>来源</dt><dd title={clip.source_name}>{clip.source_name}</dd>
      <dt>文件</dt><dd title={clip.name}>{clip.name}</dd>
    </dl>
    {(clip.recognition != null || clip.title_resolution != null) && <ClipEvidence clip={clip} />}
  </>;
}

export function ClipRow(props: ClipRowProps) {
  const { jobId, clip, canEdit, onEdit } = props;
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
      <div className="clip-row-actions">
        {canEdit && <IconButton label={`编辑 ${title}`} onClick={() => onEdit(clip)}><Icon name="edit" /></IconButton>}
        <ActionLink className="clip-download" href={clipUrl(jobId, clip.id, true)} download={clip.name}
          aria-label={`下载 ${clip.title || clip.name}`}><Icon name="download" /><span>下载</span></ActionLink>
      </div>
    </div>
    <div id={detailsId} className="clip-details" hidden={!open}>{open && <ClipDetails {...props} />}</div>
  </article>;
}
