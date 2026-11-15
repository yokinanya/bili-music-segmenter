import { token } from './api';

export interface CatalogSong { readonly id: string; readonly provider: string; readonly title: string; readonly artist: string; readonly album: string }

export async function fetchLyrics(song: CatalogSong, signal: AbortSignal): Promise<{ lyrics: string; translation: string; source: string }> {
  const response = await fetch('/api/songs/lyrics', { method: 'POST', signal,
    headers: { 'Content-Type': 'application/json', 'X-WebUI-Token': token },
    body: JSON.stringify({ id: song.id, title: song.title, artist: song.artist }),
  });
  const data = await response.json();
  if (!response.ok) throw new Error(data.error ?? `歌词查询失败：${response.status}`);
  return data;
}

export async function searchSongs(query: string, signal: AbortSignal): Promise<{ songs: CatalogSong[]; errors: { provider: string; error: string }[] }> {
  const response = await fetch(`/api/songs/search?${new URLSearchParams({ q: query })}`, {
    headers: { 'X-WebUI-Token': token }, signal,
  });
  const data = await response.json();
  if (!response.ok) throw new Error(data.error ?? `搜索失败：${response.status}`);
  return data;
}
