'use client';
import { useRef, useState } from 'react';
import { bytes } from '@/lib/format';
import type { useDraft } from '@/lib/useDraft';
import { Button, IconButton, Progress } from './Material';
import { Icon } from './Icon';
type Draft = ReturnType<typeof useDraft>;
export function ImportPanel({ draft, busy }: { draft: Draft; busy: boolean }) {
  const input = useRef<HTMLInputElement>(null);
  const [drag, setDrag] = useState(false);
  const reselectInput = useRef<HTMLInputElement>(null);
  const reselectKey = useRef<string | null>(null);
  return <section className="import-panel" aria-labelledby="import-title">
    <div className="section-head"><h2 id="import-title">导入媒体</h2><span className="counter">{draft.files.length}</span></div>
    <input hidden ref={input} type="file" multiple accept="video/*,audio/*,.mkv,.flv,.ts" onChange={(event) => { if (event.target.files) draft.add(event.target.files); event.target.value = ''; }} />
    <input hidden ref={reselectInput} type="file" accept="video/*,audio/*,.mkv,.flv,.ts" onChange={(event) => {
      const file = event.target.files?.[0];
      if (file && reselectKey.current) draft.reselect(reselectKey.current, file);
      event.target.value = ''; reselectKey.current = null;
    }} />
    <Button variant="text" disabled={busy} className={`drop-zone ${drag ? 'dragging' : ''}`} onClick={() => input.current?.click()}
      onDragOver={(event) => { event.preventDefault(); setDrag(true); }} onDragLeave={() => setDrag(false)}
      onDrop={(event) => { event.preventDefault(); setDrag(false); if (!busy) draft.add(event.dataTransfer.files); }}>
      <Icon name="upload" /><strong>选择或拖入媒体</strong>
    </Button>
    {draft.error && <div className="error" role="alert">{draft.error}<Button onClick={() => void draft.refresh()}>重新读取</Button></div>}
    <ol className="file-list">
      {draft.files.map((file, index) => <li key={file.key} className="file-row">
        <span className="file-index">{String(index + 1).padStart(2, '0')}</span>
        <div className="file-description"><strong title={file.name}>{file.name}</strong><span className="muted">{bytes(file.size)} · {file.state === 'ready' ? '已就绪' : file.state === 'uploading' ? `上传 ${bytes(file.sent)} / ${bytes(file.size)}` : file.state === 'cancelled' ? '上传已取消' : file.state === 'failed' ? '上传失败' : '等待上传'}</span>
          {file.state === 'uploading' && <Progress value={file.sent / file.size} label={`${file.name} 上传进度`} />}
          {file.error && <span className="error-text">{file.error}</span>}
        </div>
        <div className="file-actions">
          {file.state === 'uploading' ? <IconButton label="取消上传" onClick={() => draft.cancel(file.key)}><Icon name="stop" /></IconButton> : <>
            <IconButton label="上移" disabled={busy || index === 0} onClick={() => draft.move(file.key, -1)}><Icon name="up" /></IconButton>
            <IconButton label="下移" disabled={busy || index === draft.files.length - 1} onClick={() => draft.move(file.key, 1)}><Icon name="down" /></IconButton>
            <IconButton label="移除文件" disabled={busy} onClick={() => void draft.remove(file)}><Icon name="close" /></IconButton>
          </>}
          {['pending', 'failed', 'cancelled'].includes(file.state) && !file.file && <Button disabled={busy} variant="text" onClick={() => {
            reselectKey.current = file.key; reselectInput.current?.click();
          }}>重新选择原文件</Button>}
          {['failed', 'cancelled'].includes(file.state) && file.file && <Button disabled={busy} variant="text" onClick={() => void draft.retry(file)}>重试上传</Button>}
        </div>
      </li>)}
    </ol>
  </section>;
}
