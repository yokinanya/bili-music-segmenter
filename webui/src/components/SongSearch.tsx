'use client';
import { useEffect, useRef, useState, type FormEvent } from 'react';
import { searchSongs, type CatalogSong } from '@/lib/songSearch';
import { errorText } from '@/lib/format';
import { Icon } from './Icon';
import { SongLyrics } from './SongLyrics';
import { Button, IconButton, TextField } from './Material';

interface Props { initialQuery?: string; onChoose?: (song: CatalogSong) => void }

export function SongSearch({ initialQuery = '', onChoose }: Props) {
  const [query, setQuery] = useState(initialQuery), [songs, setSongs] = useState<CatalogSong[] | null>(null);
  const [busy, setBusy] = useState(false), [error, setError] = useState(''), [providerErrors, setProviderErrors] = useState<string[]>([]);
  const request = useRef<AbortController | null>(null);
  useEffect(() => () => request.current?.abort(), []);
  const search = async (event: FormEvent) => {
    event.preventDefault();
    request.current?.abort();
    const controller = new AbortController();
    request.current = controller;
    setBusy(true); setError(''); setProviderErrors([]); setSongs(null);
    try {
      const results = await searchSongs(query.trim(), controller.signal);
      if (!controller.signal.aborted) { setSongs(results.songs); setProviderErrors(results.errors.map(item => `${item.provider}：${item.error}`)); }
    } catch (cause) {
      if (!controller.signal.aborted) setError(errorText(cause));
    } finally {
      if (!controller.signal.aborted) setBusy(false);
    }
  };
  return <section className="song-search" aria-label="在线搜索歌曲">
    <form className="song-search-form" onSubmit={event => void search(event)}>
      <TextField label="歌名或歌手" value={query} onChange={setQuery} />
      <IconButton type="submit" disabled={!query.trim() || busy} label="搜索歌曲"><Icon name="search" size="sm" /></IconButton>
    </form>
    {busy && <p role="status">正在搜索…</p>}
    {error && <p className="error" role="alert">{error}</p>}
    {providerErrors.map(value => <p className="error" role="alert" key={value}>{value}</p>)}
    {songs?.length === 0 && <p role="status">没有找到歌曲，请更换关键词。</p>}
    <div className="song-search-results">{songs?.map(song => <div className="song-search-result" key={song.id}>
      <div className="song-result-info"><strong>{song.title}</strong><small>{song.provider} · {song.artist}{song.album ? ` · ${song.album}` : ''}</small></div>
      <SongLyrics song={song}>
        {onChoose && <Button variant="outlined" onClick={() => onChoose(song)}>使用此歌名</Button>}
      </SongLyrics>
    </div>)}</div>
  </section>;
}
