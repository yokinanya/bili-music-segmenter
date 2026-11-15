'use client';
import { useState } from 'react';
import type { CatalogSong } from '@/lib/songSearch';
import { Button, MaterialDialog } from './Material';
import { SongSearch } from './SongSearch';

interface Props { initialQuery: string; onChoose: (song: CatalogSong) => void }

export function SongSearchDialog({ initialQuery, onChoose }: Props) {
  const [open, setOpen] = useState(false);
  const choose = (song: CatalogSong) => { onChoose(song); setOpen(false); };
  return <>
    <Button variant="outlined" onClick={() => setOpen(true)}>搜索歌曲</Button>
    <MaterialDialog open={open} title="搜索歌曲" onClose={() => setOpen(false)}
      actions={<Button variant="text" onClick={() => setOpen(false)}>关闭</Button>}>
      {open && <div className="song-search-dialog">
        <SongSearch initialQuery={initialQuery} onChoose={choose} />
      </div>}
    </MaterialDialog>
  </>;
}
