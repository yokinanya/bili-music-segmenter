'use client';
import { useRef, useState, type FormEvent, type ReactNode } from 'react';
import { api } from '@/lib/api';
import { errorText } from '@/lib/format';
import type { RunOptions } from '@/lib/types';
import { validateParameters } from '@/lib/parameterValidation';
import { Button, TextField } from './Material';
import { Disclosure } from './Disclosure';
import { Icon } from './Icon';
interface DownloadPanelProps {
  url: string; onUrlChange: (value: string) => void;
  options: RunOptions | null; onStarted: (id: string) => void; children?: ReactNode;
}
function useDownloadSubmission({ url, options, onStarted }: DownloadPanelProps) {
  const [cookie, setCookie] = useState(''), [busy, setBusy] = useState(false), [error, setError] = useState('');
  const request = useRef<{ stamp: string; id: string } | null>(null);
  const start = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!validateParameters(event.currentTarget) || !options || busy) return;
    setBusy(true); setError('');
    try {
      const stamp = JSON.stringify([url, cookie, options]);
      if (request.current?.stamp !== stamp) request.current = { stamp, id: crypto.randomUUID() };
      const result = await api.download({ url: url.trim(), cookie, options, request_id: request.current.id });
      onStarted(result.id); setCookie(''); request.current = null;
    } catch (cause) { setError(errorText(cause)); }
    finally { setBusy(false); }
  };
  const importCookie = async (file?: File) => {
    try { if (file) setCookie(await file.text()); }
    catch (cause) { setError(errorText(cause)); }
  };
  return { cookie, setCookie, busy, error, start, importCookie };
}
export function DownloadPanel(props: DownloadPanelProps) {
  const { url, onUrlChange, options, children } = props;
  const { cookie, setCookie, busy, error, start, importCookie } = useDownloadSubmission(props);
  const cookieFile = useRef<HTMLInputElement>(null);
  return <form className="download-panel" noValidate onSubmit={(event) => void start(event)}>
    <div className="input-scroll">
      <section aria-labelledby="download-title"><div className="section-head"><h2 id="download-title">链接下载</h2></div>
        <TextField label="视频链接" type="url" required pattern="https?://.+" value={url} disabled={busy} onChange={onUrlChange} />
        <p className="helper">填完整链接，以 http:// 或 https:// 开头。</p>
        <Disclosure title={`下载 Cookie${cookie ? ' · 已填入' : '（可选）'}`}>
          <TextField label="Cookie 或 cookies.txt 内容" type="textarea" rows={3} value={cookie} disabled={busy} autocomplete="off" onChange={setCookie} />
          <input hidden ref={cookieFile} type="file" accept=".txt" disabled={busy} onChange={(event) => {
            const file = event.target.files?.[0]; event.target.value = ''; void importCookie(file);
          }} />
          <div className="cookie-actions">
            <Button type="button" variant="outlined" disabled={busy} onClick={() => cookieFile.current?.click()}><Icon name="upload" />导入 cookies.txt</Button>
            <Button type="button" variant="text" disabled={busy || !cookie} onClick={() => setCookie('')}>清空 Cookie</Button>
          </div>
          <p className="helper">Cookie 只存在服务端，用于续跑，删除任务时清除。</p>
        </Disclosure>
      </section>
      {children}
    </div>
    <div className="pane-footer">
      {error && <div className="error" role="alert">{error}</div>}
      <Button type="submit" variant="filled" disabled={!options || busy}><Icon name="download" />{busy ? '正在提交…' : '下载、合并并切片'}</Button>
    </div>
  </form>;
}
