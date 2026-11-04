'use client';
import { useRef, useState } from 'react';
import { api } from '@/lib/api';
import { errorText } from '@/lib/format';
import type { RunOptions } from '@/lib/types';
import { Button, TextField } from './Material';
import { Disclosure } from './Disclosure';
import { Icon } from './Icon';
export function DownloadPanel({ options, onStarted }: { options: RunOptions | null; onStarted: (id: string) => void }) {
  const [url, setUrl] = useState(''), [cookie, setCookie] = useState(''), [busy, setBusy] = useState(false), [error, setError] = useState('');
  const request = useRef<{ stamp: string; id: string } | null>(null);
  const cookieFile = useRef<HTMLInputElement>(null);
  const start = async () => {
    if (!options || busy) return;
    setBusy(true); setError('');
    try {
      const stamp = JSON.stringify([url, cookie, options]);
      if (request.current?.stamp !== stamp) request.current = { stamp, id: crypto.randomUUID() };
      const result = await api.download({ url, cookie, options, request_id: request.current.id });
      onStarted(result.id); setCookie(''); request.current = null;
    } catch (cause) { setError(errorText(cause)); }
    finally { setBusy(false); }
  };
  return <section className="download-panel"><div className="section-head"><h2>链接下载</h2></div>
    <TextField label="视频链接" type="url" value={url} disabled={busy} onChange={setUrl} />
    <Disclosure title={`下载 Cookie${cookie ? ' · 已填入' : '（可选）'}`}>
      <TextField label="Cookie 或 cookies.txt 内容" type="textarea" rows={3} value={cookie} disabled={busy} autocomplete="off" onChange={setCookie} />
      <input hidden ref={cookieFile} type="file" accept=".txt" onChange={async (event) => { try { const file = event.target.files?.[0]; if (file) setCookie(await file.text()); event.target.value = ''; } catch (cause) { setError(errorText(cause)); } }} />
      <Button variant="outlined" disabled={busy} onClick={() => cookieFile.current?.click()}><Icon name="upload" />导入 cookies.txt</Button>
      <p className="helper">Cookie 随源文件保留以便续跑，删除任务时清理。浏览器不保存 Cookie。</p>
    </Disclosure>
    {error && <div className="error" role="alert">{error}</div>}
    <Button variant="filled" disabled={!options || !url.trim() || busy} onClick={() => void start()}><Icon name="download" />{busy ? '正在提交…' : '下载、合并并切片'}</Button>
  </section>;
}
