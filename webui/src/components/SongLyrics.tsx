'use client';
import { useEffect, useRef, useState, type ReactNode } from 'react';
import { fetchLyrics, type CatalogSong } from '@/lib/songSearch';
import { errorText } from '@/lib/format';
import { Button } from './Material';

export function SongLyrics({ song, children }: { song: CatalogSong; children?: ReactNode }) {
  const [result, setResult] = useState<{ lyrics: string; translation: string; source: string } | null>(null);
  const [busy, setBusy] = useState(false), [error, setError] = useState('');
  const [expanded, setExpanded] = useState(false);
  const controller = useRef<AbortController | null>(null);
  useEffect(() => () => controller.current?.abort(), []);
  const load = async () => {
    controller.current?.abort();
    const request = new AbortController(); controller.current = request;
    setBusy(true); setError('');
    try { const value = await fetchLyrics(song, request.signal); if (!request.signal.aborted) { setResult(value); setExpanded(true); } }
    catch (cause) { if (!request.signal.aborted) setError(errorText(cause)); }
    finally { if (!request.signal.aborted) setBusy(false); }
  };
  return <div className="song-lyrics">
    <div className="song-result-actions"><Button variant="text" disabled={busy} aria-expanded={expanded} onClick={() => {
      if (result) setExpanded(value => !value); else void load();
    }}>{busy ? '读取中…' : expanded ? '收起歌词' : '查看歌词'}</Button>{children}</div>
    {error && <p role="alert" className="error">{error}</p>}
    {result && expanded && <div className="song-lyrics-content"><small>{result.source}</small>
      <pre>{result.lyrics || '暂无歌词'}</pre>{result.translation && <pre>{result.translation}</pre>}
    </div>}
  </div>;
}
