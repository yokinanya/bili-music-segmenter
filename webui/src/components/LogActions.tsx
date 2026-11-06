import { useEffect, useRef, useState } from 'react';
import { api } from '@/lib/api';
import { errorText } from '@/lib/format';
import { Button } from './Material';
import { readLogSnapshot } from './logBuffer';

const DOWNLOAD_URL_LIFETIME_MS = 1000;
function downloadLog(segments: string[], filename: string) {
  const url = URL.createObjectURL(new Blob(segments, { type: 'text/plain;charset=utf-8' }));
  const anchor = document.createElement('a');
  anchor.href = url; anchor.download = filename;
  document.body.append(anchor); anchor.click(); anchor.remove();
  setTimeout(() => URL.revokeObjectURL(url), DOWNLOAD_URL_LIFETIME_MS);
}

export function LogActions({ jobId, index }: { jobId: string; index: number }) {
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState('');
  const [error, setError] = useState('');
  const alive = useRef(true);
  useEffect(() => { alive.current = true; return () => { alive.current = false; }; }, []);
  const exportLog = async (copy: boolean) => {
    setBusy(true); setMessage('正在读取当前完整日志…'); setError('');
    try {
      const segments = await readLogSnapshot(offset => api.log(jobId, index, offset));
      if (!alive.current) return;
      if (copy) {
        if (!navigator.clipboard) throw new Error('当前环境不支持剪贴板，请使用下载完整日志');
        await navigator.clipboard.writeText(segments.join(''));
      } else downloadLog(segments, `${jobId}-${index + 1}.log`);
      setMessage(copy ? '已复制当前完整日志' : '已下载当前完整日志');
    } catch (cause) { if (alive.current) { setError(errorText(cause)); setMessage(''); } }
    finally { if (alive.current) setBusy(false); }
  };
  return <>
    <div className="log-actions">
      <Button variant="text" disabled={busy} onClick={() => void exportLog(true)}>复制完整日志</Button>
      <Button variant="text" disabled={busy} onClick={() => void exportLog(false)}>下载完整日志</Button>
    </div>
    {message && <p role="status" className="log-status">{message}（运行中日志以读取到末尾时为准）</p>}
    {error && <p role="alert" className="error">日志导出失败：{error}</p>}
  </>;
}
