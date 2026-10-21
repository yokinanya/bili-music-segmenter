'use client';

import { useState } from 'react';
import { clipUrl } from '@/lib/api';
import type { Clip } from '@/lib/types';

export function formatDuration(seconds: number): string {
  const total = Math.max(0, Math.round(seconds));
  const minutes = Math.floor(total / 60);
  const rest = total % 60;
  return `${minutes}:${String(rest).padStart(2, '0')}`;
}

export function ClipList({ jobId, clips }: { jobId: string; clips: Clip[] }) {
  const [playing, setPlaying] = useState<string | null>(null);
  return (
    <div className="clips">
      <h3>已导出片段（{clips.length}）</h3>
      <ul>
        {clips.map((clip) => (
          <li key={clip.path}>
            <div className="clip-row">
              <span className="file-name" title={clip.path}>
                {clip.title ? `${clip.title}${clip.artist ? ` · ${clip.artist}` : ''}` : clip.name}
              </span>
              <span className="muted small">{formatDuration(clip.duration_seconds)}</span>
              <button
                type="button"
                className="btn ghost small"
                onClick={() => setPlaying(playing === clip.name ? null : clip.name)}
              >
                {playing === clip.name ? '收起' : '试听'}
              </button>
              <a className="btn ghost small" href={clipUrl(jobId, clip.name, true)} download>
                下载
              </a>
            </div>
            {playing === clip.name && (
              // Preload metadata only: the server supports Range requests, so seeking stays cheap.
              <video className="clip-player" controls preload="metadata" src={clipUrl(jobId, clip.name)}>
                浏览器不支持内嵌播放，请使用下载。
              </video>
            )}
          </li>
        ))}
      </ul>
    </div>
  );
}
